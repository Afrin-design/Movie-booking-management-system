import re
import base64
import secrets
import string
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from database.db import db
from models.movie_model    import Movie
from models.theater_model  import Theater
from models.show_model     import Show
from models.user_model     import User
from models.booking_model  import Booking
from models.payment_model  import Payment
from models.screen_model   import Screen
from models.seats_model    import Seat
from models.message_model  import Message
from models.carousel_model import CarouselSlide
from datetime import date
import sqlalchemy as sa

admin_bp = Blueprint("admin", __name__)


# ── Guard ──────────────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _next_user_id():
    rows  = db.session.query(User.user_id).all()
    max_n = 0
    for (uid,) in rows:
        m = re.match(r"^US_(\d+)$", uid or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"US_{max_n + 1}"


def _gen_temp_password(length=10):
    chars = string.ascii_letters + string.digits + "!@#$"
    return "".join(secrets.choice(chars) for _ in range(length))


# ── Dashboard ──────────────────────────────────────────────────────────────────
@admin_bp.route("/")
@admin_required
def dashboard():
    total_revenue = db.session.query(
        sa.func.coalesce(
            sa.func.sum(
                sa.cast(Show.price_per_ticket, sa.Numeric) * Booking.total_tickets
            ), 0
        )
    ).select_from(Payment)\
     .join(Booking, Booking.booking_id == Payment.booking_id)\
     .join(Show,    Show.show_id       == Booking.show_id)\
     .filter(Payment.transaction_status == "Success")\
     .scalar() or 0

    stats = {
        "movies":        Movie.query.count(),
        "theaters":      Theater.query.count(),
        "users":         User.query.filter(User.role == "user").count(),
        "active_users":  User.query.filter(
                             User.role == "user",
                             User.password_hash.isnot(None),
                             User.password_hash != ""
                         ).count(),
        "bookings":      Booking.query.count(),
        "real_bookings": (Booking.query
                             .join(Booking.user)
                             .filter(
                                 User.password_hash.isnot(None),
                                 User.password_hash != ""
                             ).count()),
        "paid_bookings": Payment.query.filter_by(transaction_status="Success").count(),
        "revenue":       float(total_revenue),
        "owners":        User.query.filter_by(role="theater_owner").count(),
        "shows":         Show.query.count(),
        "payments":      Payment.query.filter_by(transaction_status="Success").count(),
    }

    recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(10).all()

    genre_revenue = db.session.query(
        Movie.genre,
        sa.func.coalesce(
            sa.func.sum(
                sa.cast(Show.price_per_ticket, sa.Numeric) * Booking.total_tickets
            ), 0
        ).label("revenue")
    ).select_from(Payment)\
     .join(Booking, Booking.booking_id == Payment.booking_id)\
     .join(Show,    Show.show_id       == Booking.show_id)\
     .join(Movie,   Movie.movie_id     == Show.movie_id)\
     .filter(Payment.transaction_status == "Success")\
     .group_by(Movie.genre)\
     .order_by(sa.desc("revenue"))\
     .all()

    monthly_bookings = db.session.query(
        sa.func.extract("year",  Booking.booking_date).label("yr"),
        sa.func.extract("month", Booking.booking_date).label("mo"),
        sa.func.count(Booking.booking_id).label("count")
    ).filter(Booking.booking_date.isnot(None))\
     .group_by("yr", "mo")\
     .order_by("yr", "mo")\
     .limit(12).all()

    genre_revenue_json    = [{"genre": g or "Unknown", "revenue": float(r)} for g, r in genre_revenue]
    monthly_bookings_json = [
        {"month": f"{int(yr):04d}-{int(mo):02d}", "count": int(c)}
        for yr, mo, c in monthly_bookings
    ]

    unread_count = Message.query.filter_by(is_read=False).count()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_bookings=recent_bookings,
        genre_revenue=genre_revenue,
        monthly_bookings=monthly_bookings,
        genre_revenue_json=genre_revenue_json,
        monthly_bookings_json=monthly_bookings_json,
        unread_count=unread_count,
    )


# ══════ MOVIES ════════════════════════════════════════════════════════════════
@admin_bp.route("/movies")
@admin_required
def movies():
    page   = request.args.get("page", 1, type=int)
    movies = Movie.query.order_by(Movie.release_date.desc()).paginate(page=page, per_page=15)
    return render_template("admin/movies.html", movies=movies)


@admin_bp.route("/movies/add", methods=["GET", "POST"])
@admin_required
def add_movie():
    if request.method == "POST":
        rows  = db.session.query(Movie.movie_id).all()
        max_n = max((int(re.sub(r"\D", "", uid)) for (uid,) in rows if re.search(r"\d+", uid or "")), default=0)
        movie = Movie(
            movie_id     = f"MV_{max_n + 1}",
            title        = request.form["title"],
            genre        = request.form["genre"],
            language     = request.form["language"],
            duration     = request.form.get("duration", type=int),
            rating       = request.form.get("rating", type=float),
            release_date = date.fromisoformat(request.form["release_date"]) if request.form.get("release_date") else None,
            description  = request.form.get("description"),
        )
        db.session.add(movie)
        db.session.commit()
        flash(f"Movie '{movie.title}' added.", "success")
        return redirect(url_for("admin.movies"))
    return render_template("admin/movie_form.html", movie=None, action="Add")


@admin_bp.route("/movies/<movie_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_movie(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    if request.method == "POST":
        movie.title        = request.form["title"]
        movie.genre        = request.form["genre"]
        movie.language     = request.form["language"]
        movie.duration     = request.form.get("duration", type=int)
        movie.rating       = request.form.get("rating", type=float)
        movie.release_date = date.fromisoformat(request.form["release_date"]) if request.form.get("release_date") else movie.release_date
        movie.description  = request.form.get("description")
        db.session.commit()
        flash("Movie updated.", "success")
        return redirect(url_for("admin.movies"))
    return render_template("admin/movie_form.html", movie=movie, action="Edit")


@admin_bp.route("/movies/<movie_id>/delete", methods=["POST"])
@admin_required
def delete_movie(movie_id):
    """
    BUG 4 FIX: Cascade manually before deleting the Movie.
    Movie → Shows → Bookings → Payments / Seats(nullify)
    """
    movie = Movie.query.get_or_404(movie_id)

    show_ids    = [s.show_id    for s in movie.shows]
    booking_ids = []
    for show_id in show_ids:
        booking_ids += [b.booking_id for b in Booking.query.filter_by(show_id=show_id).all()]

    if booking_ids:
        Payment.query.filter(Payment.booking_id.in_(booking_ids)).delete(synchronize_session=False)
        Seat.query.filter(Seat.booking_id.in_(booking_ids)).update({"booking_id": None}, synchronize_session=False)
        Booking.query.filter(Booking.booking_id.in_(booking_ids)).delete(synchronize_session=False)

    # Shows cascade to bookings already handled; now delete the movie (cascade="all,delete-orphan" on shows)
    db.session.delete(movie)
    db.session.commit()
    flash(f"Movie '{movie.title}' deleted.", "warning")
    return redirect(url_for("admin.movies"))


# ══════ THEATERS ══════════════════════════════════════════════════════════════
@admin_bp.route("/theaters")
@admin_required
def theaters():
    sel_city   = request.args.get("city", "")
    page       = request.args.get("page", 1, type=int)
    per_page   = 15
    query      = Theater.query
    if sel_city:
        query = query.filter_by(city=sel_city)
    all_cities     = [c[0] for c in db.session.query(Theater.city).distinct().all() if c[0]]
    theaters_page  = query.order_by(Theater.city, Theater.name).paginate(page=page, per_page=per_page, error_out=False)
    all_owners     = User.query.filter_by(role="theater_owner").order_by(User.name).all()
    return render_template("admin/theaters.html",
                           theaters=theaters_page.items,
                           pagination=theaters_page,
                           all_cities=all_cities, selected_city=sel_city,
                           all_owners=all_owners)


@admin_bp.route("/theaters/add", methods=["GET", "POST"])
@admin_required
def add_theater():
    owners = User.query.filter_by(role="theater_owner").order_by(User.name).all()
    if request.method == "POST":
        rows  = db.session.query(Theater.theater_id).all()
        max_n = max((int(re.sub(r"\D", "", uid)) for (uid,) in rows if re.search(r"\d+", uid or "")), default=0)
        owner_id = request.form.get("owner_id") or None
        # Sync brand_id from the assigned owner so _my_theaters() works correctly
        brand_id = None
        if owner_id:
            assigned_owner = User.query.get(owner_id)
            if assigned_owner:
                brand_id = assigned_owner.brand_id
        theater = Theater(
            theater_id = f"TH_{max_n + 1}",
            name       = request.form["name"],
            location   = request.form["location"],
            city       = request.form["city"],
            state      = request.form["state"],
            status     = request.form.get("status", "Active"),
            owner_id   = owner_id,
            brand_id   = brand_id,
        )
        db.session.add(theater)
        db.session.commit()
        print(f"[DEBUG add_theater] owner_id={owner_id}, brand_id={brand_id}, theater_id={theater.theater_id}")
        flash(f"Theater '{theater.name}' added.", "success")
        return redirect(url_for("admin.theaters"))
    return render_template("admin/theater_form.html", theater=None, action="Add", owners=owners)


@admin_bp.route("/theaters/<theater_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_theater(theater_id):
    theater = Theater.query.get_or_404(theater_id)
    owners  = User.query.filter_by(role="theater_owner").order_by(User.name).all()
    if request.method == "POST":
        theater.name     = request.form["name"]
        theater.location = request.form["location"]
        theater.city     = request.form["city"]
        theater.state    = request.form["state"]
        theater.status   = request.form.get("status", "Active")
        new_owner_id     = request.form.get("owner_id") or None
        theater.owner_id = new_owner_id
        # Sync brand_id from the assigned owner so _my_theaters() works correctly
        if new_owner_id:
            assigned_owner = User.query.get(new_owner_id)
            if assigned_owner and assigned_owner.brand_id:
                theater.brand_id = assigned_owner.brand_id
        elif not new_owner_id:
            # Only clear brand_id if it wasn't set independently
            pass  # Keep brand_id if theater is brand-managed
        db.session.commit()
        print(f"[DEBUG edit_theater] owner_id={theater.owner_id}, brand_id={theater.brand_id}, theater_id={theater_id}")
        flash("Theater updated.", "success")
        return redirect(url_for("admin.theaters"))
    return render_template("admin/theater_form.html", theater=theater, action="Edit", owners=owners)


@admin_bp.route("/theaters/<theater_id>/delete", methods=["POST"])
@admin_required
def delete_theater(theater_id):
    """
    BUG 4 FIX: Full manual cascade.
    Order: Payments → nullify Seat.booking_id → Bookings → Seats → Screens → Theater.
    (Shows are covered by cascade="all,delete-orphan" on Theater.shows relationship.)
    """
    theater = Theater.query.get_or_404(theater_id)

    # Collect all show_ids and booking_ids for this theater
    show_ids    = [s.show_id for s in theater.shows]
    booking_ids = []
    for show_id in show_ids:
        booking_ids += [b.booking_id for b in Booking.query.filter_by(show_id=show_id).all()]

    if booking_ids:
        Payment.query.filter(Payment.booking_id.in_(booking_ids)).delete(synchronize_session=False)
        Seat.query.filter(Seat.booking_id.in_(booking_ids)).update({"booking_id": None}, synchronize_session=False)
        Booking.query.filter(Booking.booking_id.in_(booking_ids)).delete(synchronize_session=False)

    # Delete seats for all screens of this theater
    screen_ids = [sc.screen_id for sc in theater.screens]
    if screen_ids:
        Seat.query.filter(Seat.screen_id.in_(screen_ids)).delete(synchronize_session=False)

    # Now delete the theater — cascade on relationships deletes screens & shows
    db.session.delete(theater)
    db.session.commit()
    flash(f"Theater '{theater.name}' deleted.", "warning")
    return redirect(url_for("admin.theaters"))


# ══════ USERS / CREATE OWNER ══════════════════════════════════════════════════
@admin_bp.route("/users")
@admin_required
def users():
    role     = request.args.get("role", "")
    page     = request.args.get("page", 1, type=int)
    per_page = 20
    query    = User.query
    if role:
        query = query.filter_by(role=role)
    users_page = query.order_by(User.name).paginate(page=page, per_page=per_page, error_out=False)
    return render_template("admin/users.html", users=users_page.items,
                           pagination=users_page, selected_role=role)


@admin_bp.route("/users/create-owner", methods=["GET", "POST"])
@admin_required
def create_owner():
    if request.method == "POST":
        name  = request.form.get("name",  "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()

        if not name or not email:
            flash("Name and email are required.", "danger")
            return render_template("admin/create_owner.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("admin/create_owner.html")

        temp_pwd = _gen_temp_password()
        owner = User(
            user_id              = _next_user_id(),
            name                 = name,
            email                = email,
            phone_number         = phone,
            role                 = "theater_owner",
            must_change_password = True,
        )
        owner.set_password(temp_pwd)
        db.session.add(owner)
        db.session.commit()

        from routes.auth import _send_mail
        sent = _send_mail(
            to_email = email,
            subject  = "Your CineHub Theater Owner Account",
            body     = (
                f"Hello {name},\n\n"
                f"Your Theater Owner account has been created.\n\n"
                f"Email    : {email}\n"
                f"Password : {temp_pwd}\n\n"
                f"Please log in and change your password immediately.\n\n"
                f"— CineHub Admin"
            )
        )
        if sent:
            flash(f"Owner '{name}' created. Credentials emailed to {email}.", "success")
        else:
            flash(f"Owner '{name}' created. Temp password: {temp_pwd} (share manually!)", "warning")
        return redirect(url_for("admin.users"))

    return render_template("admin/create_owner.html")


@admin_bp.route("/users/<user_id>/set-role", methods=["POST"])
@admin_required
def set_user_role(user_id):
    user      = User.query.get_or_404(user_id)
    user.role = request.form["role"]
    db.session.commit()
    flash(f"{user.name}'s role updated to {user.role}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f"User '{user.name}' deleted.", "warning")
    return redirect(url_for("admin.users"))


# ══════ SHOWS ════════════════════════════════════════════════════════════════


@admin_bp.route("/theaters/<theater_id>/assign-owner", methods=["POST"])
@login_required
def assign_theater_owner(theater_id):
    """Quick inline owner assignment from the theaters list page."""
    if current_user.role != "admin":
        abort(403)
    theater  = Theater.query.get_or_404(theater_id)
    owner_id = request.form.get("owner_id") or None
    theater.owner_id = owner_id
    # Sync brand_id so _my_theaters() (brand OR owner_id union) works correctly
    if owner_id:
        assigned_owner = User.query.get(owner_id)
        if assigned_owner and assigned_owner.brand_id:
            theater.brand_id = assigned_owner.brand_id
    db.session.commit()
    print(f"[DEBUG assign_theater_owner] theater_id={theater_id}, owner_id={owner_id}, brand_id={theater.brand_id}")
    owner_name = theater.owner.name if theater.owner else "Unassigned"
    flash(f"Owner updated to {owner_name} for {theater.name}", "success")
    return redirect(url_for("admin.theaters"))

@admin_bp.route("/shows")
@admin_required
def shows():
    from datetime import datetime as _dt
    now   = _dt.now()
    shows = Show.query.order_by(Show.show_date.desc(), Show.start_time).limit(200).all()
    return render_template("admin/shows.html", shows=shows, now=now)


# ─── BULK SHOW SLOTS DEFINITION ──────────────────────────────────────────────
SHOW_SLOTS = [
    ("Morning",    "10:00"),
    ("Matinee",    "13:00"),
    ("Evening",    "16:00"),
    ("Night",      "19:00"),
    ("Late Night", "22:00"),
]


def _next_show_num():
    """Return the current maximum show number using a single SQL MAX query.
    Avoids loading every show_id into Python memory (was O(n) full table scan).
    SH_10001 → extracts 10001 via SUBSTR and MAX in one DB round-trip.
    """
    try:
        result = db.session.execute(
            db.text("SELECT MAX(CAST(SUBSTR(show_id, 4) AS INTEGER)) FROM shows WHERE show_id LIKE 'SH_%'")
        ).scalar()
        return int(result) if result else 0
    except Exception:
        # Fallback for non-SQLite engines or unexpected IDs
        rows = db.session.query(Show.show_id).all()
        return max((int(re.sub(r"\D", "", uid)) for (uid,) in rows if re.search(r"\d+", uid or "")), default=0)


@admin_bp.route("/shows/add", methods=["GET", "POST"])
@admin_required
def add_show():
    from datetime import datetime as _dt, timedelta as _td
    # Do NOT load all movies/theaters — page would time out with 10k+ records.
    # The template uses AJAX search endpoints instead.
    screens  = Screen.query.all()

    if request.method == "POST":
        action     = request.form.get("action", "generate")
        movie_id   = request.form.get("movie_id", "")
        theater_id = request.form.get("theater_id", "")
        screen_id  = request.form.get("screen_id", "")
        price      = request.form.get("price_per_ticket", type=float) or 0
        slots_sel  = request.form.getlist("slots")

        try:
            start_date = date.fromisoformat(request.form.get("start_date", ""))
            end_date   = date.fromisoformat(request.form.get("end_date", ""))
        except ValueError:
            flash("Invalid date range.", "danger")
            return redirect(url_for("admin.add_show"))

        screen = Screen.query.get_or_404(screen_id)
        cap    = screen.total_seats or 100

        if end_date < start_date:
            flash("End date must be on or after start date.", "danger")
            return redirect(url_for("admin.add_show"))
        if not slots_sel:
            flash("Select at least one show slot.", "danger")
            return redirect(url_for("admin.add_show"))

        slot_map  = dict(SHOW_SLOTS)
        delta     = (end_date - start_date).days + 1
        to_insert = []
        skipped   = 0

        # ── ONE query to fetch all existing (show_date, start_time) pairs ────
        # Replaces N+1 individual Show.query.filter_by().first() calls.
        existing_pairs = set(
            db.session.query(Show.show_date, Show.start_time)
            .filter(
                Show.screen_id == screen_id,
                Show.show_date >= start_date,
                Show.show_date <= end_date,
            )
            .all()
        )

        for day_offset in range(delta):
            cur_date = start_date + _td(days=day_offset)
            for slot_name in slots_sel:
                time_str = slot_map.get(slot_name)
                if not time_str:
                    continue
                if (cur_date, time_str) in existing_pairs:   # O(1) set lookup
                    skipped += 1
                    continue
                to_insert.append((cur_date, slot_name, time_str))

        if action == "preview":
            preview = [
                {"date": d.strftime("%d %b %Y"), "slot": sl, "time": _dt.strptime(t, "%H:%M").strftime("%I:%M %p")}
                for d, sl, t in to_insert
            ]
            return jsonify({"preview": preview, "skipped": skipped, "total": len(to_insert)})

        max_n   = _next_show_num()
        created = len(to_insert)

        # ── Bulk insert: one DB round-trip instead of one INSERT per show ─────
        show_records = []
        for cur_date, slot_name, time_str in to_insert:
            max_n += 1
            show_records.append({
                "show_id":          f"SH_{max_n}",
                "movie_id":         movie_id,
                "theater_id":       theater_id,
                "screen_id":        screen_id,
                "show_date":        cur_date,
                "start_time":       time_str,
                "price_per_ticket": price,
                "available_seats":  cap,
            })

        if show_records:
            db.session.bulk_insert_mappings(Show, show_records)
        db.session.commit()
        msg = f"✅ {created} show(s) generated successfully!"
        if skipped:
            msg += f" ({skipped} duplicate(s) skipped)"
        flash(msg, "success")
        return jsonify({"success": True, "created": created, "skipped": skipped, "message": msg})

    return render_template("admin/show_form.html",
                           slots=SHOW_SLOTS,
                           today=date.today().isoformat())


@admin_bp.route("/api/screens-by-theater/<theater_id>")
@admin_required
def api_screens_by_theater(theater_id):
    screens = Screen.query.filter_by(theater_id=theater_id).all()
    return jsonify([
        {"screen_id": s.screen_id, "screen_number": s.screen_number, "total_seats": s.total_seats}
        for s in screens
    ])


# ══════ ALL BOOKINGS ══════════════════════════════════════════════════════════
@admin_bp.route("/bookings")
@admin_required
def all_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template("admin/all_bookings.html", bookings=bookings)


# ══════ MESSAGES ══════════════════════════════════════════════════════════════
@admin_bp.route("/messages")
@admin_required
def messages():
    msgs   = Message.query.order_by(Message.created_at.desc()).all()
    unread = [m for m in msgs if not m.is_read]
    for m in unread:
        m.is_read = True
    if unread:
        db.session.commit()
    return render_template("admin/messages.html", messages=msgs)


@admin_bp.route("/messages/<int:msg_id>/delete", methods=["POST"])
@admin_required
def delete_message(msg_id):
    msg = Message.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.", "warning")
    return redirect(url_for("admin.messages"))


@admin_bp.route("/messages/reply", methods=["POST"])
@admin_required
def reply_message():
    """Send an email reply to a contact message sender."""
    to_email   = request.form.get("to_email", "").strip()
    subject    = request.form.get("subject", "Re: Your message").strip()
    reply_body = request.form.get("reply_body", "").strip()

    if not to_email or not reply_body:
        flash("Reply could not be sent — missing fields.", "danger")
        return redirect(url_for("admin.messages"))

    from routes.auth import _send_mail
    full_body = (
        f"{reply_body}\n\n"
        "---\n"
        "CineHub Support Team\n"
        "This is a reply to your contact form submission."
    )
    sent = _send_mail(to_email=to_email, subject=subject, body=full_body)
    if sent:
        flash(f"Reply sent to {to_email} successfully.", "success")
    else:
        flash(f"Could not send email to {to_email}. Check mail configuration.", "danger")
    return redirect(url_for("admin.messages"))


# ══════ CAROUSEL ══════════════════════════════════════════════════════════════

@admin_bp.route("/carousel")
@admin_required
def carousel():
    slides = CarouselSlide.query\
        .join(Movie, Movie.movie_id == CarouselSlide.movie_id)\
        .add_columns(Movie.title, Movie.genre, Movie.rating)\
        .order_by(CarouselSlide.display_order.asc(), CarouselSlide.id.asc())\
        .all()
    # Flatten to attribute-accessible objects
    slide_list = []
    for row in slides:
        s = row[0]
        s.title  = row.title
        s.genre  = row.genre
        s.rating = row.rating
        slide_list.append(s)
    return render_template("admin/carousel.html", slides=slide_list)


@admin_bp.route("/carousel/add", methods=["POST"])
@admin_required
def carousel_add():
    try:
        movie_id      = request.form.get("movie_id", "").strip()
        badge_label   = request.form.get("badge_label", "NOW SHOWING").strip()
        image_url     = request.form.get("image_url", "").strip() or None
        trailer_url   = request.form.get("trailer_url", "").strip() or None
        display_order = int(request.form.get("display_order", 0) or 0)

        if not movie_id:
            return jsonify({"success": False, "message": "Please select a movie."}), 400

        if not Movie.query.get(movie_id):
            return jsonify({"success": False, "message": "Movie not found."}), 404

        image_data = None
        file = request.files.get("image_file")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in {"jpg", "jpeg", "png", "gif", "webp"}:
                return jsonify({"success": False, "message": "Only JPG, PNG, GIF, WEBP images allowed."}), 400
            raw = file.read()
            if len(raw) > 5 * 1024 * 1024:
                return jsonify({"success": False, "message": "Image must be under 5 MB."}), 400
            mime = f"image/{'jpeg' if ext == 'jpg' else ext}"
            image_data = "data:" + mime + ";base64," + base64.b64encode(raw).decode()
            image_url  = None

        slide = CarouselSlide(
            movie_id      = movie_id,
            badge_label   = badge_label or "NOW SHOWING",
            image_url     = image_url,
            image_data    = image_data,
            trailer_url   = trailer_url,
            display_order = display_order,
            is_active     = True,
        )
        db.session.add(slide)
        db.session.commit()
        return jsonify({"success": True, "message": "Slide added to carousel!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route("/carousel/<int:slide_id>/edit", methods=["POST"])
@admin_required
def carousel_edit(slide_id):
    slide = CarouselSlide.query.get_or_404(slide_id)
    try:
        badge_label   = (request.form.get("badge_label") or slide.badge_label or "NOW SHOWING").strip()
        display_order = int(request.form.get("display_order") or slide.display_order or 0)
        image_url     = request.form.get("image_url", "").strip() or None
        trailer_url   = request.form.get("trailer_url", "").strip() or None

        file = request.files.get("image_file")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            raw = file.read()
            mime = f"image/{'jpeg' if ext == 'jpg' else ext}"
            slide.image_data = "data:" + mime + ";base64," + base64.b64encode(raw).decode()
            slide.image_url  = None
        elif image_url:
            slide.image_url  = image_url
            slide.image_data = None

        slide.badge_label   = badge_label
        slide.display_order = display_order
        slide.trailer_url   = trailer_url
        db.session.commit()
        return jsonify({"success": True, "message": "Slide updated."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route("/carousel/<int:slide_id>/toggle", methods=["POST"])
@admin_required
def carousel_toggle(slide_id):
    slide = CarouselSlide.query.get_or_404(slide_id)
    try:
        slide.is_active = not slide.is_active
        db.session.commit()
        status = "activated" if slide.is_active else "deactivated"
        return jsonify({"success": True, "message": f"Slide {status}.", "is_active": slide.is_active})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route("/carousel/<int:slide_id>/delete", methods=["POST"])
@admin_required
def carousel_delete(slide_id):
    slide = CarouselSlide.query.get_or_404(slide_id)
    try:
        db.session.delete(slide)
        db.session.commit()
        return jsonify({"success": True, "message": "Slide removed from carousel."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500



@admin_bp.route("/api/movie-search")
@admin_required
def api_movie_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    movies = Movie.query.filter(Movie.title.ilike(f"%{q}%")).order_by(Movie.title).limit(20).all()
    return jsonify([{"movie_id": m.movie_id, "title": m.title, "genre": m.genre or "", "language": m.language or ""} for m in movies])


@admin_bp.route("/api/theater-search")
@admin_required
def api_theater_search():
    q = request.args.get("q", "").strip()
    if not q:
        theaters = Theater.query.order_by(Theater.city, Theater.name).limit(20).all()
    else:
        theaters = Theater.query.filter(
            db.or_(Theater.name.ilike(f"%{q}%"), Theater.city.ilike(f"%{q}%"))
        ).order_by(Theater.city, Theater.name).limit(20).all()
    return jsonify([{"theater_id": t.theater_id, "name": t.name, "city": t.city} for t in theaters])


@admin_bp.route("/api/all-movies")
@admin_required
def api_all_movies():
    movies = Movie.query.order_by(Movie.title).all()
    return jsonify([{"movie_id": m.movie_id, "title": m.title, "language": m.language or "", "genre": m.genre or ""} for m in movies])


@admin_bp.route("/api/all-theaters")
@admin_required
def api_all_theaters():
    theaters = Theater.query.filter_by(status="Active").order_by(Theater.city, Theater.name).all()
    return jsonify([{"theater_id": t.theater_id, "name": t.name, "city": t.city or ""} for t in theaters])

# ─── AUTO-GENERATE SHOWS FOR ALL MOVIES × ALL THEATERS (next 7 days) ─────────


# ─── AUTO-GENERATE SHOWS FOR ALL MOVIES × ALL THEATERS (next 7 days) ─────────


# ══════════════════════════════════════════════════════════════════════════════
# REFUND MANAGEMENT — Admin
# ══════════════════════════════════════════════════════════════════════════════

@admin_bp.route("/refunds")
@admin_required
def refund_management():
    """List all cancellation requests pending admin action."""
    status_filter = request.args.get("status", "all")

    q = Booking.query.filter(
        Booking.payment_status.in_(["CANCELLED", "REFUNDED", "Cancelled - Refund Initiated"])
    ).order_by(Booking.cancelled_at.desc())

    if status_filter == "pending":
        q = q.filter(Booking.refund_status == "PENDING")
    elif status_filter == "approved":
        q = q.filter(Booking.refund_status == "APPROVED")
    elif status_filter == "rejected":
        q = q.filter(Booking.refund_status == "REJECTED")

    bookings = q.all()
    stats = {
        "total":    Booking.query.filter(Booking.refund_status.isnot(None)).count(),
        "pending":  Booking.query.filter(Booking.refund_status == "PENDING").count(),
        "approved": Booking.query.filter(Booking.refund_status == "APPROVED").count(),
        "rejected": Booking.query.filter(Booking.refund_status == "REJECTED").count(),
    }
    return render_template("admin/refund_management.html",
                           bookings=bookings, stats=stats,
                           status_filter=status_filter)


@admin_bp.route("/refunds/<booking_id>/approve", methods=["POST"])
@admin_required
def approve_refund(booking_id):
    """Admin approves a refund request → status becomes REFUNDED."""
    booking = Booking.query.get_or_404(booking_id)
    if booking.refund_status not in ("PENDING", None):
        flash("This refund has already been processed.", "warning")
        return redirect(url_for("admin.refund_management"))

    booking.refund_status   = "APPROVED"
    booking.payment_status  = "REFUNDED"
    db.session.commit()

    # Notify user
    try:
        from routes.auth import _send_mail
        if booking.user:
            _send_mail(
                to_email=booking.user.email,
                subject="Refund Approved — CineHub",
                body=(
                    f"Hi {booking.user.name},\n\n"
                    f"Your refund for booking #{booking.booking_id} has been APPROVED.\n"
                    f"Refund Amount: ₹{float(booking.refund_amount or 0):.2f}\n"
                    "The amount will be credited to your original payment source within 5-7 business days.\n\n"
                    "— CineHub Support"
                )
            )
    except Exception:
        pass

    flash(f"Refund approved for booking {booking_id}.", "success")
    return redirect(url_for("admin.refund_management"))


@admin_bp.route("/refunds/<booking_id>/reject", methods=["POST"])
@admin_required
def reject_refund(booking_id):
    """Admin rejects a refund request."""
    booking = Booking.query.get_or_404(booking_id)
    if booking.refund_status not in ("PENDING", None):
        flash("This refund has already been processed.", "warning")
        return redirect(url_for("admin.refund_management"))

    rejection_reason = request.form.get("reason", "").strip() or "Policy violation"

    booking.refund_status       = "REJECTED"
    booking.cancellation_reason = (booking.cancellation_reason or "") + f" | Rejected: {rejection_reason}"
    db.session.commit()

    try:
        from routes.auth import _send_mail
        if booking.user:
            _send_mail(
                to_email=booking.user.email,
                subject="Refund Request Rejected — CineHub",
                body=(
                    f"Hi {booking.user.name},\n\n"
                    f"Unfortunately, your refund request for booking #{booking.booking_id} has been REJECTED.\n"
                    f"Reason: {rejection_reason}\n\n"
                    "If you believe this is an error, please contact support.\n\n"
                    "— CineHub Support"
                )
            )
    except Exception:
        pass

    flash(f"Refund rejected for booking {booking_id}.", "warning")
    return redirect(url_for("admin.refund_management"))
