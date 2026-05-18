import re
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from database.db import db
from models.theater_model import Theater
from models.screen_model  import Screen
from models.show_model    import Show
from models.movie_model   import Movie
from models.booking_model import Booking
from models.payment_model import Payment
from models.seats_model   import Seat
from models.user_model    import User
from models.brand_model   import TheaterBrand
from datetime import date
import sqlalchemy as sa

owner_bp = Blueprint("owner", __name__)


# ══════════════════════════════════════════════════════════════════════════════
# GUARDS & SCOPE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def owner_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "theater_owner":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _my_theater_filter():
    """
    Returns a SQLAlchemy WHERE clause (BinaryExpression) that restricts
    Theater rows to those owned by the current user.
    Using a filter expression (not a Python list) avoids giant IN(…) clauses
    that time-out on PostgreSQL when an owner has hundreds of theaters.
    """
    from sqlalchemy import or_
    brand_id = getattr(current_user, "brand_id", None)
    uid      = current_user.user_id
    if brand_id:
        return or_(Theater.brand_id == brand_id, Theater.owner_id == uid)
    return Theater.owner_id == uid


def _my_theater_subq():
    """
    Returns a subquery of theater_id values for the current owner.
    Use with .filter(SomeModel.theater_id.in_(_my_theater_subq()))
    — the IN is evaluated inside the DB, no giant parameter lists.
    """
    return db.session.query(Theater.theater_id).filter(_my_theater_filter()).subquery()


def _my_theaters():
    """Return Theater ORM objects for this owner (used where full objects needed)."""
    return Theater.query.filter(_my_theater_filter()).all()


def _my_theater_ids():
    """
    Returns a list of theater_id strings.
    ⚠️  Only call this where you NEED a Python list (e.g. passing to templates).
    For DB queries prefer _my_theater_subq() to avoid huge IN() lists.
    """
    return [row[0] for row in
            db.session.query(Theater.theater_id).filter(_my_theater_filter()).all()]


def _assert_owns_theater(theater_id):
    """403 if the theater does not belong to the current owner (via brand_id OR owner_id)."""
    t        = Theater.query.get_or_404(theater_id)
    brand_id = getattr(current_user, "brand_id", None)
    uid      = current_user.user_id
    # Union check: access granted if matched by brand OR by direct owner assignment
    if brand_id and t.brand_id == brand_id:
        return t
    if t.owner_id == uid:
        return t
    abort(403)


def _assert_owns_screen(screen_id):
    screen = Screen.query.get_or_404(screen_id)
    _assert_owns_theater(screen.theater_id)
    return screen


# ── ID helpers ─────────────────────────────────────────────────────────────────
def _next_id(model, id_col, prefix):
    rows  = db.session.query(id_col).all()
    max_n = max(
        (int(re.sub(r"\D", "", uid)) for (uid,) in rows if re.search(r"\d+", uid or "")),
        default=0
    )
    return f"{prefix}{max_n + 1}"


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@owner_bp.route("/")
@owner_required
def dashboard():
    """Renders instantly — only fast COUNT queries on page load. Revenue loaded via AJAX."""
    from datetime import datetime, timedelta
    theaters = _my_theaters()
    brand    = getattr(current_user, "brand", None)

    if not theaters:
        flash("No theater assigned to your account yet. Contact admin.", "warning")
        return render_template("theater/dashboard.html",
                               theaters=[], stats={}, upcoming_shows=[],
                               brand=brand)

    # Use subquery to avoid massive IN(id1, id2, ...) lists that timeout on PostgreSQL
    theater_sq = _my_theater_subq()
    now         = datetime.now()
    week_ago    = now - timedelta(days=7)
    prev_week   = now - timedelta(days=14)

    # Fast COUNT-only queries (no table scan)
    total_bookings     = Booking.query.join(Booking.show).filter(Show.theater_id.in_(theater_sq)).count()
    real_bookings      = (Booking.query
                            .join(Booking.show)
                            .join(Booking.user)
                            .filter(
                                Show.theater_id.in_(theater_sq),
                                User.password_hash.isnot(None),
                                User.password_hash != ""
                            ).count())
    screens_count      = Screen.query.filter(Screen.theater_id.in_(theater_sq)).count()
    shows_count        = Show.query.filter(Show.theater_id.in_(theater_sq)).count()
    this_week_bookings = Booking.query.join(Booking.show).filter(
        Show.theater_id.in_(theater_sq), Booking.booking_date >= week_ago.date()).count()
    prev_week_bookings = Booking.query.join(Booking.show).filter(
        Show.theater_id.in_(theater_sq),
        Booking.booking_date >= prev_week.date(),
        Booking.booking_date <  week_ago.date()).count()

    wow_pct = 0
    if prev_week_bookings:
        wow_pct = round((this_week_bookings - prev_week_bookings) / prev_week_bookings * 100, 1)

    # Revenue: try fast query with statement_timeout, fallback to 0 (shown as "Loading…" in UI)
    try:
        from sqlalchemy import text as _text
        db.session.execute(_text("SET LOCAL statement_timeout = '3s'"))
        owner_revenue = db.session.query(
            sa.func.coalesce(
                sa.func.sum(sa.cast(Show.price_per_ticket, sa.Numeric) * Booking.total_tickets), 0)
        ).select_from(Payment)         .join(Booking, Booking.booking_id == Payment.booking_id)         .join(Show,    Show.show_id       == Booking.show_id)         .filter(Payment.transaction_status == "Success", Show.theater_id.in_(theater_sq))         .scalar() or 0
    except Exception:
        db.session.rollback()
        owner_revenue = -1   # signals template to show "—"

    # Only latest 10 upcoming shows (fast — uses index)
    upcoming_shows = (
        Show.query.filter(Show.theater_id.in_(theater_sq),
                          Show.show_date >= now.date())
            .order_by(Show.show_date, Show.start_time).limit(10).all()
    )

    stats = {
        "theaters":       len(theaters),
        "total_bookings": total_bookings,
        "real_bookings":  real_bookings,
        "revenue":        float(owner_revenue) if owner_revenue >= 0 else None,
        "screens":        screens_count,
        "shows":          shows_count,
        "this_week":      this_week_bookings,
        "wow_pct":        wow_pct,
    }

    return render_template("theater/dashboard.html",
                           theaters=theaters, stats=stats,
                           upcoming_shows=upcoming_shows,
                           brand=brand)


@owner_bp.route("/api/dashboard-revenue")
@owner_required
def api_dashboard_revenue():
    """AJAX endpoint — returns revenue separately so dashboard loads fast."""
    theater_sq = _my_theater_subq()
    try:
        revenue = db.session.query(
            sa.func.coalesce(
                sa.func.sum(sa.cast(Show.price_per_ticket, sa.Numeric) * Booking.total_tickets), 0)
        ).select_from(Payment)         .join(Booking, Booking.booking_id == Payment.booking_id)         .join(Show,    Show.show_id       == Booking.show_id)         .filter(Payment.transaction_status == "Success", Show.theater_id.in_(theater_sq))         .scalar() or 0
        return jsonify({"revenue": float(revenue)})
    except Exception as e:
        return jsonify({"revenue": 0, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# SCREENS
# ══════════════════════════════════════════════════════════════════════════════

@owner_bp.route("/screens")
@owner_required
def screens():
    tid     = _my_theater_subq()
    screens = (Screen.query.filter(Screen.theater_id.in_(tid))
                     .order_by(Screen.theater_id, Screen.screen_number).all())
    theaters = _my_theaters()
    return render_template("theater/screens.html",
                           screens=screens, theaters=theaters)


@owner_bp.route("/screens/add", methods=["GET", "POST"])
@owner_required
def add_screen():
    theaters = _my_theaters()
    if not theaters:
        flash("No theater assigned. Contact admin.", "warning")
        return redirect(url_for("owner.dashboard"))

    if request.method == "POST":
        theater_id    = request.form.get("theater_id")
        _assert_owns_theater(theater_id)          # brand-scope guard

        screen_number = int(request.form.get("screen_number", 1) or 1)
        gold_count    = int(request.form.get("gold_seats",    0) or 0)
        silver_count  = int(request.form.get("silver_seats",  0) or 0)
        gen_count     = int(request.form.get("general_seats", 0) or 0)

        if gold_count + silver_count + gen_count == 0:
            flash("At least one seat must be added.", "danger")
            return render_template("theater/screen_form.html", theaters=theaters)

        screen_id = _next_id(Screen, Screen.screen_id, "SCR")
        screen = Screen(
            screen_id     = screen_id,
            theater_id    = theater_id,
            screen_number = screen_number,
            gold_seats    = gold_count,
            silver_seats  = silver_count,
            general_seats = gen_count,
            total_seats   = gold_count + silver_count + gen_count,
        )
        db.session.add(screen)
        db.session.flush()

        _generate_seats_for_screen(screen_id, gold_count, silver_count, gen_count)
        db.session.commit()
        flash(f"Screen #{screen_number} added with {screen.total_seats} seats.", "success")
        return redirect(url_for("owner.screens"))

    return render_template("theater/screen_form.html", theaters=theaters)


@owner_bp.route("/screens/<screen_id>/edit", methods=["GET", "POST"])
@owner_required
def edit_screen(screen_id):
    screen   = _assert_owns_screen(screen_id)
    theaters = _my_theaters()

    if request.method == "POST":
        new_tid = request.form.get("theater_id")
        _assert_owns_theater(new_tid)

        screen.theater_id    = new_tid
        screen.screen_number = int(request.form.get("screen_number", screen.screen_number) or screen.screen_number)
        gold_count           = int(request.form.get("gold_seats",    screen.gold_seats)    or 0)
        silver_count         = int(request.form.get("silver_seats",  screen.silver_seats)  or 0)
        gen_count            = int(request.form.get("general_seats", screen.general_seats) or 0)
        screen.gold_seats    = gold_count
        screen.silver_seats  = silver_count
        screen.general_seats = gen_count
        screen.total_seats   = gold_count + silver_count + gen_count
        db.session.commit()
        flash("Screen updated.", "success")
        return redirect(url_for("owner.screens"))

    return render_template("theater/screen_form.html",
                           screen=screen, theaters=theaters)


@owner_bp.route("/screens/<screen_id>/delete", methods=["POST"])
@owner_required
def delete_screen(screen_id):
    screen = _assert_owns_screen(screen_id)
    has_shows = Show.query.filter_by(screen_id=screen_id).count()
    if has_shows:
        flash("Cannot delete screen — it has shows scheduled.", "danger")
        return redirect(url_for("owner.screens"))
    num = screen.screen_number
    db.session.delete(screen)
    db.session.commit()
    flash(f"Screen #{num} deleted.", "warning")
    return redirect(url_for("owner.screens"))


@owner_bp.route("/api/generate-seats/<screen_id>", methods=["POST"])
@owner_required
def api_generate_seats(screen_id):
    _assert_owns_screen(screen_id)
    gold   = int(request.json.get("gold",    0))
    silver = int(request.json.get("silver",  0))
    gen    = int(request.json.get("general", 0))
    Seat.query.filter_by(screen_id=screen_id).delete()
    _generate_seats_for_screen(screen_id, gold, silver, gen)
    db.session.commit()
    return jsonify({"ok": True, "total": gold + silver + gen})


# ══════════════════════════════════════════════════════════════════════════════
# SHOWS
# ══════════════════════════════════════════════════════════════════════════════

@owner_bp.route("/shows")
@owner_required
def shows():
    from datetime import datetime, timedelta
    tid   = _my_theater_subq()
    brand = getattr(current_user, "brand", None)
    now   = datetime.now()

    # Paginate — only load 50 shows per page instead of all
    page     = request.args.get("page", 1, type=int)
    per_page = 50
    shows_pg = (
        Show.query.filter(Show.theater_id.in_(tid))
            .order_by(Show.show_date.desc(), Show.start_time)
            .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Stats via COUNT queries — no full table load
    week_end       = (now + timedelta(days=7)).date()
    total_count    = Show.query.filter(Show.theater_id.in_(tid)).count()
    upcoming_count = Show.query.filter(Show.theater_id.in_(tid),
                                       Show.show_date >= now.date()).count()
    this_week_count= Show.query.filter(Show.theater_id.in_(tid),
                                       Show.show_date >= now.date(),
                                       Show.show_date <= week_end).count()

    top_movie_row = (
        db.session.query(Movie.title, sa.func.count(Booking.booking_id).label("cnt"))
        .join(Show,    Show.movie_id   == Movie.movie_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Show.theater_id.in_(tid))
        .group_by(Movie.title)
        .order_by(sa.desc("cnt")).first()
    )
    top_movie = top_movie_row.title if top_movie_row else "—"

    avg_tickets = (
        db.session.query(sa.func.avg(Booking.total_tickets))
        .join(Show, Show.show_id == Booking.show_id)
        .filter(Show.theater_id.in_(tid)).scalar() or 0
    )

    show_stats = {
        "total":       total_count,
        "upcoming":    upcoming_count,
        "this_week":   this_week_count,
        "top_movie":   top_movie,
        "avg_tickets": round(float(avg_tickets), 1),
    }

    return render_template("theater/shows.html",
                           shows=shows_pg.items,
                           pagination=shows_pg,
                           show_stats=show_stats,
                           brand=brand)


@owner_bp.route("/shows/add", methods=["GET", "POST"])
@owner_required
def add_show():
    from datetime import datetime as _dt, timedelta as _td
    tid      = _my_theater_subq()
    theaters = _my_theaters()
    # Do NOT load all movies upfront — use AJAX search instead (/owner/api/movie-search)

    OWNER_SLOTS = [
        ("Morning",    "10:00"),
        ("Matinee",    "13:00"),
        ("Evening",    "16:00"),
        ("Night",      "19:00"),
        ("Late Night", "22:00"),
    ]

    if request.method == "POST":
        action     = request.form.get("action", "generate")
        theater_id = request.form.get("theater_id")
        _assert_owns_theater(theater_id)

        screen_id  = request.form.get("screen_id")
        screen     = Screen.query.get_or_404(screen_id)
        if screen.theater_id != theater_id:
            abort(403)

        price     = request.form.get("price_per_ticket", type=float) or 0
        slots_sel = request.form.getlist("slots")
        cap       = screen.total_seats or 100

        try:
            start_date = date.fromisoformat(request.form.get("start_date", ""))
            end_date   = date.fromisoformat(request.form.get("end_date", ""))
        except ValueError:
            flash("Invalid date range.", "danger")
            return redirect(url_for("owner.add_show"))

        if end_date < start_date:
            flash("End date must be on or after start date.", "danger")
            return redirect(url_for("owner.add_show"))
        if not slots_sel:
            flash("Select at least one show slot.", "danger")
            return redirect(url_for("owner.add_show"))

        slot_map  = dict(OWNER_SLOTS)
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

        # ── Single SQL MAX query instead of loading all show_ids into Python ──
        try:
            max_n = db.session.execute(
                db.text("SELECT MAX(CAST(SUBSTR(show_id, 4) AS INTEGER)) FROM shows WHERE show_id LIKE 'SH_%'")
            ).scalar() or 0
            max_n = int(max_n)
        except Exception:
            rows  = db.session.query(Show.show_id).all()
            max_n = max((int(re.sub(r"\D", "", uid)) for (uid,) in rows if re.search(r"\d+", uid or "")), default=0)

        movie_id = request.form.get("movie_id")
        created  = len(to_insert)

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

    screens = Screen.query.filter(Screen.theater_id.in_(tid))\
                          .order_by(Screen.theater_id, Screen.screen_number).all()
    return render_template("theater/show_form.html",
                           theaters=theaters, screens=screens,
                           slots=OWNER_SLOTS, today=date.today().isoformat())


@owner_bp.route("/api/movie-search")
@owner_required
def api_movie_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    movies = Movie.query.filter(Movie.title.ilike(f"%{q}%")).order_by(Movie.title).limit(20).all()
    return jsonify([{"movie_id": m.movie_id, "title": m.title, "language": m.language or ""} for m in movies])


@owner_bp.route("/shows/<show_id>/delete", methods=["POST"])
@owner_required
def delete_show(show_id):
    show = Show.query.get_or_404(show_id)
    _assert_owns_theater(show.theater_id)

    has_bookings = Booking.query.filter_by(show_id=show_id).count()
    if has_bookings:
        flash("Cannot delete show — bookings exist.", "danger")
        return redirect(url_for("owner.shows"))

    Seat.query.filter_by(show_id=show_id).update(
        {"status": "Available"}, synchronize_session="fetch"
    )
    db.session.delete(show)
    db.session.commit()
    flash("Show deleted.", "warning")
    return redirect(url_for("owner.shows"))


# ══════════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ══════════════════════════════════════════════════════════════════════════════

@owner_bp.route("/bookings")
@owner_required
def bookings():
    tid      = _my_theater_subq()
    page     = request.args.get("page", 1, type=int)
    per_page = 50
    bk_pg = (
        Booking.query.join(Booking.show)
        .filter(Show.theater_id.in_(tid))
        .order_by(Booking.booking_date.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return render_template("theater/bookings.html",
                           bookings=bk_pg.items,
                           pagination=bk_pg,
                           brand=getattr(current_user, "brand", None))


# ══════════════════════════════════════════════════════════════════════════════
# API helpers (used by show_form AJAX)
# ══════════════════════════════════════════════════════════════════════════════

@owner_bp.route("/api/screens-by-theater/<theater_id>")
@owner_required
def api_screens_by_theater(theater_id):
    _assert_owns_theater(theater_id)
    screens = Screen.query.filter_by(theater_id=theater_id).all()
    return jsonify([
        {"screen_id": s.screen_id, "screen_number": s.screen_number,
         "total_seats": s.total_seats,
         "gold_seats": s.gold_seats, "silver_seats": s.silver_seats,
         "general_seats": s.general_seats}
        for s in screens
    ])


# ══════════════════════════════════════════════════════════════════════════════
# SEAT GENERATION HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _generate_seats_for_screen(screen_id, gold_count, silver_count, general_count):
    from models.seats_model import Seat

    def _next_seat_id():
        rows  = db.session.query(Seat.seat_id).all()
        max_n = max(
            (int(re.sub(r"\D", "", sid)) for (sid,) in rows if re.search(r"\d+", sid or "")),
            default=0,
        )
        return max_n + 1

    counter = _next_seat_id()
    configs = [
        ("Gold",    gold_count,    150),
        ("Silver",  silver_count,  100),
        ("General", general_count, 60),
    ]
    COLS = 10
    for seat_type, count, charge in configs:
        for i in range(count):
            row_letter = chr(65 + i // COLS)
            seat_num   = (i % COLS) + 1
            db.session.add(Seat(
                seat_id     = f"S{counter}",
                screen_id   = screen_id,
                seat_type   = seat_type,
                seat_number = f"{row_letter}{seat_num}",
                status      = "Available",
                charges     = charge,
            ))
            counter += 1


# ══════════════════════════════════════════════════════════════════════════════
# MOVIES — Theater Owner can view movies available for their shows
# ══════════════════════════════════════════════════════════════════════════════

@owner_bp.route("/movies")
@owner_required
def owner_movies():
    """Table view of all movies — existing (from owner's shows) + all in DB for adding shows."""
    import re as _re
    from datetime import date as _date_cls
    tid      = _my_theater_subq()
    page     = request.args.get("page", 1, type=int)
    q_search = request.args.get("q", "").strip()
    tab      = request.args.get("tab", "all")   # "all" | "mine"

    # "mine" = movies that already have shows in this owner's theaters
    if tab == "mine":
        movies_q = (
            Movie.query
            .join(Show, Show.movie_id == Movie.movie_id)
            .filter(Show.theater_id.in_(tid))
            .distinct()
        )
    else:
        movies_q = Movie.query

    if q_search:
        movies_q = movies_q.filter(Movie.title.ilike(f"%{q_search}%"))

    movies = movies_q.order_by(Movie.title).paginate(page=page, per_page=20, error_out=False)

    # Show counts (only needed for "mine" tab, cheap query)
    movie_ids_on_page = [m.movie_id for m in movies.items]
    show_counts = {}
    if movie_ids_on_page and tab == "mine":
        rows = (
            db.session.query(Show.movie_id, sa.func.count(Show.show_id))
            .filter(Show.movie_id.in_(movie_ids_on_page), Show.theater_id.in_(tid))
            .group_by(Show.movie_id)
            .all()
        )
        show_counts = {mid: cnt for mid, cnt in rows}

    return render_template("theater/movies.html",
                           movies=movies.items, pagination=movies,
                           show_counts=show_counts, q_search=q_search,
                           tab=tab,
                           brand=getattr(current_user, "brand", None))


@owner_bp.route("/movies/add", methods=["GET", "POST"])
@owner_required
def owner_add_movie():
    """Theater owner adds a new movie to the database."""
    import re as _re
    from datetime import date as _date_cls
    if request.method == "POST":
        rows  = db.session.query(Movie.movie_id).all()
        max_n = max(
            (int(_re.sub(r"\D", "", uid)) for (uid,) in rows if _re.search(r"\d+", uid or "")),
            default=0
        )
        movie = Movie(
            movie_id     = f"MV_{max_n + 1:04d}",
            title        = request.form["title"].strip(),
            genre        = request.form.get("genre", "").strip() or None,
            language     = request.form.get("language", "").strip() or None,
            duration     = request.form.get("duration", type=int),
            rating       = request.form.get("rating", type=float),
            release_date = _date_cls.fromisoformat(request.form["release_date"])
                           if request.form.get("release_date") else None,
            description  = request.form.get("description", "").strip() or None,
        )
        db.session.add(movie)
        db.session.commit()
        flash(f"Movie '{movie.title}' added successfully.", "success")
        return redirect(url_for("owner.owner_movies"))
    return render_template("theater/movie_form.html",
                           movie=None, action="Add",
                           brand=getattr(current_user, "brand", None))


@owner_bp.route("/movies/<movie_id>/edit", methods=["GET", "POST"])
@owner_required
def owner_edit_movie(movie_id):
    """Theater owner edits a movie."""
    from datetime import date as _date_cls
    movie = Movie.query.get_or_404(movie_id)
    if request.method == "POST":
        movie.title        = request.form["title"].strip()
        movie.genre        = request.form.get("genre", "").strip() or None
        movie.language     = request.form.get("language", "").strip() or None
        movie.duration     = request.form.get("duration", type=int)
        movie.rating       = request.form.get("rating", type=float)
        movie.release_date = (_date_cls.fromisoformat(request.form["release_date"])
                              if request.form.get("release_date") else movie.release_date)
        movie.description  = request.form.get("description", "").strip() or None
        db.session.commit()
        flash(f"Movie '{movie.title}' updated.", "success")
        return redirect(url_for("owner.owner_movies"))
    return render_template("theater/movie_form.html",
                           movie=movie, action="Edit",
                           brand=getattr(current_user, "brand", None))


# ══════════════════════════════════════════════════════════════════════════════
# REFUND MANAGEMENT — Theater Owner view
# ══════════════════════════════════════════════════════════════════════════════

@owner_bp.route("/refunds")
@owner_required
def owner_refunds():
    """Theater owner views cancellation requests for their theater's shows."""
    from models.booking_model import Booking
    from models.show_model import Show

    tid = _my_theater_subq()
    status_filter = request.args.get("status", "all")

    q = (
        Booking.query
        .join(Booking.show)
        .filter(
            Show.theater_id.in_(tid),
            Booking.payment_status.in_(["CANCELLED", "REFUNDED", "Cancelled - Refund Initiated"])
        )
        .order_by(Booking.cancelled_at.desc())
    )

    if status_filter == "pending":
        q = q.filter(Booking.refund_status == "PENDING")
    elif status_filter == "approved":
        q = q.filter(Booking.refund_status == "APPROVED")
    elif status_filter == "rejected":
        q = q.filter(Booking.refund_status == "REJECTED")

    bookings = q.all()

    stats = {
        "total":    Booking.query.join(Booking.show).filter(Show.theater_id.in_(tid), Booking.refund_status.isnot(None)).count(),
        "pending":  Booking.query.join(Booking.show).filter(Show.theater_id.in_(tid), Booking.refund_status == "PENDING").count(),
        "approved": Booking.query.join(Booking.show).filter(Show.theater_id.in_(tid), Booking.refund_status == "APPROVED").count(),
        "rejected": Booking.query.join(Booking.show).filter(Show.theater_id.in_(tid), Booking.refund_status == "REJECTED").count(),
    }

    return render_template("theater/refunds.html",
                           bookings=bookings, stats=stats,
                           status_filter=status_filter,
                           brand=getattr(current_user, "brand", None))

