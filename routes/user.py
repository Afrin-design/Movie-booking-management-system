import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from database.db import db
from models.movie_model    import Movie
from models.theater_model  import Theater
from models.show_model     import Show
from models.booking_model  import Booking
from models.payment_model  import Payment
from models.seats_model    import Seat
from models.reviews_model  import Review
from models.carousel_model import CarouselSlide
from models.user_model     import User
from models.seat_lock_model import SeatLock, LOCK_TTL_SECONDS
from datetime import datetime, date, timedelta

user_bp = Blueprint("user", __name__)


def _next_booking_id():
    rows  = db.session.query(Booking.booking_id).all()
    max_n = max((int(re.sub(r"\D", "", uid)) for (uid,) in rows if re.search(r"\d+", uid or "")), default=0)
    return f"BK_{max_n + 1}"


# ── Booking state helpers ──────────────────────────────────────────────────────
CONFIRMED_STATUSES  = {"Completed", "CONFIRMED"}
CANCELLED_STATUSES  = {"CANCELLED", "REFUNDED", "EXPIRED"}

def _show_start_dt(show):
    """Return UTC datetime of show start, or None."""
    if not show:
        return None
    d = show.show_date_obj
    t = show.start_time_obj
    if d and t:
        return datetime.combine(d, t)
    return None


def _booking_state(booking):
    """
    Returns a dict describing the exact current state of a booking.
    Keys:
      status          – normalised status string
      show_expired    – bool: show start time has passed (UTC)
      can_pay         – bool: can user complete payment?
      can_cancel      – bool: can user cancel right now?
      cancel_blocked_reason – str or None
      refund_amount   – float >= 0
      conv_fee        – float
    """
    CONV_FEE = 30.0
    ps   = (booking.payment_status or "").strip()
    show = booking.show
    now  = datetime.now()   # local time — show times are stored as local (IST), not UTC

    sdt  = _show_start_dt(show)
    show_expired = bool(sdt and now >= sdt)

    # Auto-expire PENDING bookings whose show has passed
    if ps == "Pending" and show_expired:
        ps = "EXPIRED"

    # Normalise legacy "Completed" → CONFIRMED
    if ps == "Completed":
        ps = "CONFIRMED"

    total  = float(booking.total_amount or 0)
    conv   = float(booking.convenience_fee or CONV_FEE)
    if total <= 0 and show:
        seats  = list(booking.seats)
        base   = float(show.price_per_ticket or 0) * int(booking.total_tickets or 0)
        extra  = sum(float(s.charges or 0) for s in seats)
        total  = base + extra
    refund = max(0.0, total - conv)

    can_pay    = (ps == "Pending") and (not show_expired)
    can_cancel = False
    block_msg  = None

    if ps == "CONFIRMED":
        if show_expired:
            block_msg  = "Show has already started or completed."
        elif sdt and now >= (sdt - timedelta(minutes=30)):
            block_msg  = "Cancellation closes 30 minutes before the show."
        else:
            can_cancel = True
    elif ps == "Pending":
        block_msg = "Complete payment first before cancelling."
    elif ps in ("CANCELLED",):
        block_msg = "This booking is already cancelled."
    elif ps in ("REFUNDED",):
        block_msg = "This booking has already been refunded."
    elif ps == "EXPIRED":
        block_msg = "This booking has expired."
    else:
        block_msg = f"Cancellation not available (status: {ps})."

    return {
        "status":                ps,
        "show_expired":          show_expired,
        "can_pay":               can_pay,
        "can_cancel":            can_cancel,
        "cancel_blocked_reason": block_msg,
        "refund_amount":         refund,
        "conv_fee":              conv,
        "total_amount":          total,
    }


def _next_payment_id():
    rows  = db.session.query(Payment.payment_id).all()
    max_n = max((int(re.sub(r"\D", "", uid)) for (uid,) in rows if re.search(r"\d+", uid or "")), default=0)
    return f"PMT_{max_n + 1}"


# ── Home ───────────────────────────────────────────────────────────────────────
@user_bp.route("/")
def home():
    cities        = [c[0] for c in db.session.query(Theater.city).distinct().order_by(Theater.city).all() if c[0]]
    # Only use city from URL param — never auto-fill from user profile
    selected_city = request.args.get("city", "").strip() or None
    # ── Movies with upcoming shows — EXISTS is fast even with 350k+ shows ──
    from datetime import date as _date_cls
    _today_home = _date_cls.today()
    if selected_city:
        _has_show = (db.session.query(Show.show_id)
                     .join(Show.theater)
                     .filter(Show.movie_id   == Movie.movie_id,
                             Show.available_seats > 0,
                             Show.show_date  >= _today_home,
                             Theater.city    == selected_city)
                     .correlate(Movie).exists())
    else:
        _has_show = (db.session.query(Show.show_id)
                     .filter(Show.movie_id   == Movie.movie_id,
                             Show.available_seats > 0,
                             Show.show_date  >= _today_home)
                     .correlate(Movie).exists())
    movies_with_shows = Movie.query.order_by(Movie.rating.desc()).limit(20).all()
    featured          = movies_with_shows
    genres        = [g[0] for g in db.session.query(Movie.genre).distinct().order_by(Movie.genre).all() if g[0]]

    # Carousel: active slides (joined with movie data), fallback to top-rated movies
    active_slides = (CarouselSlide.query
                     .filter_by(is_active=True)
                     .join(Movie, Movie.movie_id == CarouselSlide.movie_id)
                     .order_by(CarouselSlide.display_order.asc())
                     .limit(10)
                     .all())

    if active_slides:
        carousel_movies = []
        for s in active_slides:
            m = s.movie
            carousel_movies.append({
                "movie_id":    m.movie_id,
                "title":       m.title,
                "genre":       m.genre,
                "language":    m.language,
                "duration":    m.duration,
                "rating":      m.rating,
                "description": m.description,
                "badge_label": s.badge_label,
                "image_url":   s.image_url,
                "image_data":  s.image_data,
                "trailer_url": s.trailer_url,
            })
    else:
        # Fallback: top 8 movies as carousel
        carousel_movies = []
        for m in Movie.query.order_by(Movie.rating.desc()).limit(8).all():
            carousel_movies.append({
                "movie_id":    m.movie_id,
                "title":       m.title,
                "genre":       m.genre,
                "language":    m.language,
                "duration":    m.duration,
                "rating":      m.rating,
                "description": m.description,
                "badge_label": "NOW SHOWING",
                "image_url":   None,
                "image_data":  None,
                "trailer_url": None,
            })

    # Build shows_map — only for the 10 featured movies shown on home page
    # Never load all 350k shows into RAM
    featured_ids = [m.movie_id for m in movies_with_shows]
    shows_map    = {}
    if featured_ids:
        from datetime import date as _date
        today    = _date.today()
        _fsq     = Show.query.filter(
            Show.available_seats > 0,
            Show.show_date      >= today,
            Show.movie_id.in_(featured_ids)
        )
        if selected_city:
            _fsq = _fsq.join(Show.theater).filter(Theater.city == selected_city)
        for s in _fsq.order_by(Show.show_date.asc(), Show.start_time.asc()).all():
            shows_map.setdefault(s.movie_id, []).append(s)

    return render_template("user/home.html",
                           cities=cities, selected_city=selected_city,
                           featured=featured, genres=genres,
                           carousel_movies=carousel_movies,
                           shows_map=shows_map,
                           stat_movies=Movie.query.count(),
                           stat_theaters=Theater.query.count(),
                           stat_bookings=Booking.query.count(),
                           stat_users=User.query.filter_by(role='user').count())


@user_bp.route("/api/theaters-in-city")
def api_theaters_in_city():
    city     = request.args.get("city", "")
    movie_id = request.args.get("movie_id", "")
    query = db.session.query(Theater).join(Show, Show.theater_id == Theater.theater_id)
    if city:
        query = query.filter(Theater.city == city)
    if movie_id:
        query = query.filter(Show.movie_id == movie_id)
    theaters = query.distinct().order_by(Theater.name).all()
    return jsonify([
        {"theater_id": t.theater_id, "name": t.name,
         "location": t.location or "", "city": t.city or ""}
        for t in theaters
    ])


@user_bp.route("/api/shows-for-theater")
def api_shows_for_theater():
    theater_id = request.args.get("theater_id", "")
    movie_id   = request.args.get("movie_id", "")
    from datetime import datetime as _dt, timedelta
    now = _dt.now()
    shows = Show.query.filter(
        Show.theater_id == theater_id,
        Show.movie_id   == movie_id,
        Show.show_date  >= now.date(),
    ).order_by(Show.show_date.asc(), Show.start_time).limit(30).all()
    # Filter out shows that started more than 30 minutes ago (allow booking up to 30 min after start)
    cutoff = (now - timedelta(minutes=30)).strftime("%H:%M")
    shows = [s for s in shows if not (
        s.show_date_obj == now.date() and s.start_time and s.start_time <= cutoff
    )]
    return jsonify([
        {
            "show_id":          s.show_id,
            "show_date":        str(s.show_date),
            "start_time":       s.start_time or "",
            "price_per_ticket": float(s.price_per_ticket or 0),
            "available_seats":  s.available_seats or 0,
        }
        for s in shows
    ])


# ── Movies list ────────────────────────────────────────────────────────────────
@user_bp.route("/movies")
def movies():
    city  = request.args.get("city",     "")
    genre = request.args.get("genre",    "")
    lang  = request.args.get("language", "")
    q     = request.args.get("q",        "").strip()
    page  = request.args.get("page", 1,  type=int)
    PER_PAGE = 24

    # Show ALL movies — filter by city only if selected
    from datetime import date as _date
    _today = _date.today()
    if city:
        _mhas = (db.session.query(Show.show_id)
                 .join(Show.theater)
                 .filter(Show.movie_id == Movie.movie_id,
                         Show.available_seats > 0,
                         Show.show_date >= _today,
                         Theater.city == city)
                 .correlate(Movie).exists())
        query = Movie.query.filter(_mhas)
    else:
        query = Movie.query
    if q:
        query = query.filter(Movie.title.ilike(f"%{q}%"))
    if genre:
        query = query.filter(Movie.genre == genre)
    if lang:
        query = query.filter(Movie.language == lang)

    total = query.count()
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page  = max(1, min(page, pages))
    items = query.order_by(Movie.rating.desc()).offset((page-1)*PER_PAGE).limit(PER_PAGE).all()

    class MoviesResult:
        def __init__(self, items, total, page, pages):
            self.items    = items
            self.total    = total
            self.pages    = pages
            self.page     = page
            self.has_prev = page > 1
            self.has_next = page < pages
    movies_page = MoviesResult(items, total, page, pages)

    cities    = [c[0] for c in db.session.query(Theater.city).distinct().all() if c[0]]
    genres    = [g[0] for g in db.session.query(Movie.genre).distinct().all() if g[0]]
    languages = [l[0] for l in db.session.query(Movie.language).distinct().all() if l[0]]
    return render_template("user/movies.html",
                           movies_page=movies_page, cities=cities,
                           genres=genres, languages=languages,
                           selected_city=city, selected_genre=genre,
                           selected_lang=lang, q=q)


@user_bp.route("/api/movies-json")
def api_movies_json():
    """JSON endpoint for fast city-based movie fetching."""
    city  = request.args.get("city",     "")
    genre = request.args.get("genre",    "")
    lang  = request.args.get("language", "")
    q     = request.args.get("q",        "").strip()
    page  = request.args.get("page", 1,  type=int)
    PER_PAGE = 24

    from datetime import date as _date
    _today_api = _date.today()
    if city:
        _ahas = (db.session.query(Show.show_id)
                 .join(Show.theater)
                 .filter(Show.movie_id == Movie.movie_id,
                         Show.available_seats > 0,
                         Show.show_date >= _today_api,
                         Theater.city == city)
                 .correlate(Movie).exists())
    else:
        _ahas = (db.session.query(Show.show_id)
                 .filter(Show.movie_id == Movie.movie_id,
                         Show.available_seats > 0,
                         Show.show_date >= _today_api)
                 .correlate(Movie).exists())
    query = Movie.query.filter(_ahas)
    if q:
        query = query.filter(Movie.title.ilike(f"%{q}%"))
    if genre:
        query = query.filter(Movie.genre == genre)
    if lang:
        query = query.filter(Movie.language == lang)

    total = query.count()
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page  = max(1, min(page, pages))
    items = query.order_by(Movie.rating.desc()).offset((page-1)*PER_PAGE).limit(PER_PAGE).all()

    return jsonify({
        "total": total,
        "page":  page,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
        "movies": [{
            "movie_id":    m.movie_id,
            "title":       m.title,
            "genre":       m.genre or "",
            "language":    m.language or "",
            "rating":      float(m.rating) if m.rating else 0,
            "duration":    m.duration or "",
        } for m in items]
    })


# ── Movie Detail ───────────────────────────────────────────────────────────────
@user_bp.route("/movies/<movie_id>")
def movie_detail(movie_id):
    from sqlalchemy import func
    movie = Movie.query.get_or_404(movie_id)
    city  = request.args.get("city", "")

    # ✅ FIX: Show next 7 days of shows, not just today
    from datetime import datetime as _dt
    _now = _dt.now()
    _today = _now.date()
    _future = _today + timedelta(days=7)
    
    shows_q = Show.query.filter(
        Show.movie_id == movie_id, 
        Show.show_date >= _today,
        Show.show_date <= _future
    )
    
    city_has_no_shows = False
    if city:
        shows = (shows_q.join(Show.theater)
                 .filter(Theater.city == city)
                 .order_by(Show.show_date.asc(), Show.start_time)
                 .limit(200).all())
        if not shows:
            city_has_no_shows = True
    else:
        shows = shows_q.order_by(Show.show_date.asc(), Show.start_time).limit(200).all()
    
    # Deduplicate: keep only 1 show per (theater, date, time) — handles repeated script runs
    _seen_key = set()
    _deduped  = []
    for s in shows:
        _key = (s.theater_id, str(s.show_date), (str(s.start_time or ''))[:5])
        if _key not in _seen_key:
            _seen_key.add(_key)
            _deduped.append(s)
    shows = _deduped

    # Filter shows that started more than 30 minutes ago
    _cutoff = (_now - timedelta(minutes=30)).strftime("%H:%M")
    shows = [s for s in shows if not (
        s.show_date_obj == _now.date() and s.start_time and str(s.start_time)[:5] <= _cutoff
    )]

    # Find which cities DO have shows for this movie (for smart suggestions)
    cities_with_shows = []
    if city_has_no_shows:
        rows = (db.session.query(Theater.city)
                .join(Show, Show.theater_id == Theater.theater_id)
                .filter(Show.movie_id == movie_id)
                .distinct().all())
        cities_with_shows = [r[0] for r in rows if r[0]]

    # ── Real available seats = total screen seats − booked seats ──────────────
    # Two bulk queries to avoid N+1
    show_ids   = [s.show_id   for s in shows]
    screen_ids = list({s.screen_id for s in shows if s.screen_id})

    # Count seats marked Booked per show (via Booking join)
    booked_counts = {}
    if show_ids:
        rows = (db.session.query(Booking.show_id, func.count(Seat.seat_id))
                .join(Seat, Seat.booking_id == Booking.booking_id)
                .filter(Booking.show_id.in_(show_ids), Seat.status == "Booked")
                .group_by(Booking.show_id).all())
        booked_counts = {r[0]: r[1] for r in rows}

    # Count total seats per screen
    total_counts = {}
    if screen_ids:
        rows2 = (db.session.query(Seat.screen_id, func.count(Seat.seat_id))
                 .filter(Seat.screen_id.in_(screen_ids))
                 .group_by(Seat.screen_id).all())
        total_counts = {r[0]: r[1] for r in rows2}

    # Build real_available dict per show_id
    real_available = {}
    for s in shows:
        total  = total_counts.get(s.screen_id) or int(s.available_seats or 0)
        booked = booked_counts.get(s.show_id, 0)
        real_available[s.show_id] = max(0, total - booked)

    reviews = (Review.query.filter_by(movie_id=movie_id)
               .order_by(Review.review_date.desc()).limit(5).all())
    cities  = [c[0] for c in db.session.query(Theater.city).distinct().all() if c[0]]

    # Group shows by theater
    shows_by_theater = {}
    for s in shows:
        tid = s.theater_id
        if tid not in shows_by_theater:
            shows_by_theater[tid] = {"theater": s.theater, "shows": []}
        shows_by_theater[tid]["shows"].append(s)

    return render_template("user/movie_detail.html",
                           movie=movie, shows=shows,
                           shows_by_theater=shows_by_theater,
                           real_available=real_available,
                           reviews=reviews, cities=cities,
                           selected_city=city, today=date.today(),
                           city_has_no_shows=city_has_no_shows,
                           cities_with_shows=cities_with_shows)


# ── Seat Selection ─────────────────────────────────────────────────────────────
@user_bp.route("/shows/<show_id>/seats")
def seat_selection(show_id):
    show   = Show.query.get_or_404(show_id)
    screen = show.screen

    # ── Step 1: auto-generate seats if screen has NONE ────────────────────────
    existing = Seat.query.filter_by(screen_id=show.screen_id).count()
    if existing == 0:
        from routes.theater_owner import _generate_seats_for_screen
        gold_n    = int(screen.gold_seats    or 0) if screen else 0
        silver_n  = int(screen.silver_seats  or 0) if screen else 0
        general_n = int(screen.general_seats or 0) if screen else 0
        if gold_n == 0 and silver_n == 0 and general_n == 0:
            total     = int(screen.total_seats or 0) if screen else 0
            general_n = total if total > 0 else int(show.available_seats or 0)
            # ── CRITICAL FIX: if everything is 0, default to 60 General seats ──
            # This happens when CSV/Excel data didn't populate seat columns.
            if general_n == 0:
                general_n = 60
        _generate_seats_for_screen(show.screen_id, gold_n, silver_n, general_n)
        new_total = gold_n + silver_n + general_n
        show.available_seats = new_total
        if screen:
            screen.total_seats   = new_total
            screen.general_seats = general_n
            screen.gold_seats    = gold_n
            screen.silver_seats  = silver_n
        db.session.commit()

    # ── Step 2: NORMALIZE seeded seats that have NULL status / seat_type ──────
    # Seeded CSVs often leave these columns NULL.  We patch them in-place once.
    null_status_seats = Seat.query.filter(
        Seat.screen_id == show.screen_id,
        Seat.status.is_(None)
    ).all()
    if null_status_seats:
        for s in null_status_seats:
            s.status = "Available"
        db.session.commit()

    null_type_seats = Seat.query.filter(
        Seat.screen_id == show.screen_id,
        Seat.seat_type.is_(None)
    ).all()
    if null_type_seats:
        for s in null_type_seats:
            s.seat_type = "Regular"
            if s.charges is None:
                s.charges = 0.0
        db.session.commit()

    # ── Step 3: load & group seats ────────────────────────────────────────────
    seats = (Seat.query
             .filter_by(screen_id=show.screen_id)
             .order_by(Seat.seat_type, Seat.seat_number).all())

    SEAT_ORDER = ["VIP", "Premium", "Regular"]
    raw_groups: dict = {}
    for seat in seats:
        key = seat.seat_type or "Regular"
        raw_groups.setdefault(key, []).append(seat)

    seat_groups = {st: raw_groups[st] for st in SEAT_ORDER if st in raw_groups}
    for st, sl in raw_groups.items():
        if st not in seat_groups:
            seat_groups[st] = sl

    # ── Build real booked seat set from Booking.seat_labels ──────────────────
    # We store the JS grid labels (e.g. "B12,B13") directly in booking.seat_labels
    # This is reliable regardless of how the DB seat_number column is formatted,
    # and works for both auto-generated seats and CSV-seeded seats.
    CANCELLED_STATUSES = ("Cancelled", "Refunded")

    booked_bookings = (
        Booking.query
        .filter(
            Booking.show_id == show_id,
            Booking.seat_labels.isnot(None),
            Booking.seat_labels != "",
        )
        .all()
    )

    booked_seat_numbers = []
    for bk in booked_bookings:
        # Skip cancelled/refunded bookings so their seats are freed
        if bk.payment_status and any(s in bk.payment_status for s in CANCELLED_STATUSES):
            continue
        labels = [lb.strip() for lb in (bk.seat_labels or "").split(",") if lb.strip()]
        booked_seat_numbers.extend(labels)

    # De-duplicate
    booked_seat_numbers = list(set(booked_seat_numbers))

    return render_template("user/seat_selection.html",
                           show=show, seat_groups=seat_groups,
                           booked_seat_numbers=booked_seat_numbers)


# ── Real-time seat status API (booked + locked) ───────────────────────────
@user_bp.route("/api/seats/<show_id>/status")
def api_seat_status(show_id):
    """
    Returns booked seat labels AND temporarily locked seat labels for a show.
    The UI polls this every 5 s to keep the seat map in sync for all viewers.

    Response shape:
        {
            "booked":          ["A1", "B3", ...],   # permanently booked
            "locked_by_others":["C4", ...],          # held by another session
            "locked_by_me":    ["D7", ...],          # held by caller's session
            "lock_ttl":        600                   # seconds a lock lives
        }
    """
    session_id = request.args.get("session_id", "")
    now        = datetime.utcnow()

    CANCELLED_STATUSES = ("Cancelled", "Refunded")

    # ── Booked seats ─────────────────────────────────────────────────────────
    booked_bookings = (
        Booking.query
        .filter(
            Booking.show_id == show_id,
            Booking.seat_labels.isnot(None),
            Booking.seat_labels != "",
        )
        .all()
    )
    booked = set()
    for bk in booked_bookings:
        if bk.payment_status and any(s in bk.payment_status for s in CANCELLED_STATUSES):
            continue
        for lb in (bk.seat_labels or "").split(","):
            lb = lb.strip()
            if lb:
                booked.add(lb)

    # ── Active seat locks ────────────────────────────────────────────────────
    active_locks = (
        SeatLock.query
        .filter(
            SeatLock.show_id    == show_id,
            SeatLock.expires_at >  now,
        )
        .all()
    )
    locked_by_me     = []
    locked_by_others = []
    for lk in active_locks:
        if lk.seat_label in booked:
            continue          # already confirmed-booked; skip the lock row
        if lk.session_id == session_id:
            locked_by_me.append(lk.seat_label)
        else:
            locked_by_others.append(lk.seat_label)

    return jsonify({
        "booked":           sorted(booked),
        "locked_by_others": locked_by_others,
        "locked_by_me":     locked_by_me,
        "lock_ttl":         LOCK_TTL_SECONDS,
    })


# Keep legacy /api/seats/<show_id> route working (polled by older templates)
@user_bp.route("/api/seats/<show_id>")
def api_seats(show_id):
    """Legacy endpoint — returns booked seats only (no lock info)."""
    show = Show.query.get_or_404(show_id)  # noqa: F841 — validates show exists
    CANCELLED_STATUSES = ("Cancelled", "Refunded")
    booked_bookings = (
        Booking.query
        .filter(
            Booking.show_id == show_id,
            Booking.seat_labels.isnot(None),
            Booking.seat_labels != "",
        )
        .all()
    )
    booked_js, seen = [], set()
    for bk in booked_bookings:
        if bk.payment_status and any(s in bk.payment_status for s in CANCELLED_STATUSES):
            continue
        for lb in (bk.seat_labels or "").split(","):
            lb = lb.strip()
            if lb and lb not in seen:
                seen.add(lb)
                booked_js.append(lb)
    return jsonify({"booked": booked_js})


# ── Lock seats API ────────────────────────────────────────────────────────────
@user_bp.route("/api/seats/<show_id>/lock", methods=["POST"])
def api_lock_seats(show_id):
    """
    Atomically lock a list of seats for a session during the payment flow.

    Request JSON:
        { "seats": ["A1", "B3"], "session_id": "<client-uuid>" }

    Response on success:
        { "success": true,  "locked": ["A1","B3"], "expires_at": "<ISO>" }

    Response on conflict:
        { "success": false, "conflicts": ["A1"],   "message": "..." }

    Uses SELECT FOR UPDATE (SQLite fallback: table-level lock via transaction)
    to prevent two concurrent requests from locking the same seat.
    """
    data       = request.get_json(force=True, silent=True) or {}
    seats      = [str(s).strip() for s in data.get("seats", []) if str(s).strip()]
    session_id = data.get("session_id", "").strip()

    if not seats or not session_id:
        return jsonify({"success": False, "message": "seats and session_id are required"}), 400

    if len(seats) > 10:
        return jsonify({"success": False, "message": "Maximum 10 seats per booking"}), 400

    show = Show.query.get(show_id)
    if not show:
        return jsonify({"success": False, "message": "Show not found"}), 404

    now        = datetime.utcnow()
    expires_at = SeatLock.make_expires()
    user_id    = current_user.user_id if current_user.is_authenticated else None

    try:
        # ── Atomic section ───────────────────────────────────────────────────
        # 1. Purge expired locks for this show (housekeeping)
        SeatLock.query.filter(
            SeatLock.show_id    == show_id,
            SeatLock.expires_at <= now,
        ).delete(synchronize_session=False)

        # 2. Find already-booked labels
        CANCELLED_STATUSES = ("Cancelled", "Refunded")
        booked_bookings = (
            Booking.query
            .filter(
                Booking.show_id == show_id,
                Booking.seat_labels.isnot(None),
                Booking.seat_labels != "",
            )
            .with_for_update()          # row-level lock (Postgres/MySQL) — ignored on SQLite
            .all()
        )
        booked_set = set()
        for bk in booked_bookings:
            if bk.payment_status and any(s in bk.payment_status for s in CANCELLED_STATUSES):
                continue
            for lb in (bk.seat_labels or "").split(","):
                lb = lb.strip()
                if lb:
                    booked_set.add(lb)

        # 3. Find seats locked by OTHER sessions
        other_locks = (
            SeatLock.query
            .filter(
                SeatLock.show_id        == show_id,
                SeatLock.seat_label.in_(seats),
                SeatLock.session_id     != session_id,
                SeatLock.expires_at     >  now,
            )
            .all()
        )
        locked_by_others = {lk.seat_label for lk in other_locks}

        # 4. Collect conflicts
        conflicts = [s for s in seats if s in booked_set or s in locked_by_others]
        if conflicts:
            db.session.rollback()
            return jsonify({
                "success":   False,
                "conflicts": conflicts,
                "message":   f"Seat(s) {', '.join(conflicts)} are already booked or held by another user.",
            }), 409

        # 5. Upsert locks owned by THIS session for each requested seat
        for seat_label in seats:
            existing = SeatLock.query.filter_by(
                show_id    = show_id,
                seat_label = seat_label,
                session_id = session_id,
            ).first()

            if existing:
                # Refresh expiry (user is still actively on the page)
                existing.expires_at = expires_at
                existing.user_id    = user_id
            else:
                import uuid as _uuid
                new_lock = SeatLock(
                    lock_id    = f"LK_{_uuid.uuid4().hex[:16]}",
                    show_id    = show_id,
                    seat_label = seat_label,
                    user_id    = user_id,
                    session_id = session_id,
                    locked_at  = now,
                    expires_at = expires_at,
                )
                db.session.add(new_lock)

        db.session.commit()
        return jsonify({
            "success":    True,
            "locked":     seats,
            "expires_at": expires_at.isoformat() + "Z",   # Z = UTC — prevents JS misreading as local time
            "lock_ttl":   LOCK_TTL_SECONDS,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Lock failed: {str(e)}"}), 500


# ── Release seats API ─────────────────────────────────────────────────────────
@user_bp.route("/api/seats/<show_id>/release", methods=["POST"])
def api_release_seats(show_id):
    """
    Release seat locks held by a session.

    Request JSON:
        { "session_id": "<uuid>", "seats": ["A1"] }  ← seats is optional
        If seats is omitted, ALL locks for this session on this show are released.

    Called when:
        - User deselects a seat (release that specific seat)
        - Payment is cancelled or fails (release all)
        - Page unload / tab close (beacon API)
    """
    data       = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id", "").strip()
    seats      = data.get("seats")   # None → release all for session

    if not session_id:
        return jsonify({"success": False, "message": "session_id is required"}), 400

    try:
        query = SeatLock.query.filter(
            SeatLock.show_id    == show_id,
            SeatLock.session_id == session_id,
        )
        if seats:
            query = query.filter(SeatLock.seat_label.in_(seats))

        deleted = query.delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"success": True, "released": deleted})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ── Book Show Simple (JS seats, text seat numbers, double-booking guard) ──────
@user_bp.route("/shows/<show_id>/book", methods=["POST"])
@login_required
def book_show_simple(show_id):
    show         = Show.query.get_or_404(show_id)
    seat_numbers = request.form.get("seat_numbers", "").strip()
    num_tickets  = int(request.form.get("num_tickets", 1) or 1)
    session_id   = request.form.get("lock_session_id", "").strip()

    if not seat_numbers or num_tickets < 1:
        flash("Please select at least one seat.", "warning")
        return redirect(url_for("user.seat_selection", show_id=show_id))

    if num_tickets > 10:
        flash("Maximum 10 seats allowed per booking.", "danger")
        return redirect(url_for("user.seat_selection", show_id=show_id))

    # Parse submitted JS labels (e.g. "A3, B12, F1")
    submitted_labels = [s.strip() for s in seat_numbers.split(",") if s.strip()]

    now = datetime.utcnow()

    # ── ATOMIC double-booking guard using DB transaction ─────────────────────
    # We do everything inside one transaction:
    #   1. Purge expired locks
    #   2. Re-verify no other session holds these seats
    #   3. Re-verify no confirmed booking exists for these seats
    #   4. Create the booking and release locks — all or nothing
    try:
        # Purge stale locks for this show
        SeatLock.query.filter(
            SeatLock.show_id    == show_id,
            SeatLock.expires_at <= now,
        ).delete(synchronize_session=False)

        CANCELLED_STATUSES = ("Cancelled", "Refunded")

        # Row-level lock on booking rows for this show (prevents concurrent writes)
        existing_bookings = (
            Booking.query
            .filter(
                Booking.show_id == show_id,
                Booking.seat_labels.isnot(None),
                Booking.seat_labels != "",
            )
            .with_for_update()
            .all()
        )

        already_booked = set()
        for bk in existing_bookings:
            if bk.payment_status and any(s in bk.payment_status for s in CANCELLED_STATUSES):
                continue
            for lb in (bk.seat_labels or "").split(","):
                lb = lb.strip()
                if lb:
                    already_booked.add(lb)

        conflicts = [lb for lb in submitted_labels if lb in already_booked]
        if conflicts:
            db.session.rollback()
            flash(
                f"Seat(s) {', '.join(conflicts)} were just booked by someone else. "
                f"Please select different seats.",
                "danger"
            )
            return redirect(url_for("user.seat_selection", show_id=show_id))

        # Check for seats locked by a DIFFERENT session (race condition guard)
        if session_id:
            rival_locks = (
                SeatLock.query
                .filter(
                    SeatLock.show_id        == show_id,
                    SeatLock.seat_label.in_(submitted_labels),
                    SeatLock.session_id     != session_id,
                    SeatLock.expires_at     >  now,
                )
                .all()
            )
            if rival_locks:
                rival_seats = [lk.seat_label for lk in rival_locks]
                db.session.rollback()
                flash(
                    f"Seat(s) {', '.join(rival_seats)} are currently held by another user. "
                    f"Please select different seats.",
                    "danger"
                )
                return redirect(url_for("user.seat_selection", show_id=show_id))

        # ── Create booking ─────────────────────────────────────────────────────
        booking_id = _next_booking_id()
        _conv_fee = 30
        booking = Booking(
            booking_id      = booking_id,
            user_id         = current_user.user_id,
            show_id         = show_id,
            booking_date    = datetime.utcnow(),
            total_tickets   = num_tickets,
            payment_status  = "Pending",
            seat_labels     = ",".join(submitted_labels),
            convenience_fee = _conv_fee,
        )
        db.session.add(booking)

        # ── Mark the corresponding DB seats as Booked ─────────────────────────
        GOLD_ROWS    = ['A']
        SILVER_ROWS  = ['B', 'C', 'D', 'E']
        GENERAL_ROWS = ['F', 'G', 'H', 'I', 'J', 'K']

        def js_label_to_db_prefix_and_type(label):
            if not label:
                return None, None
            row = label[0].upper()
            if row in ('A',):
                return 'G', 'VIP'
            elif row in ('B', 'C', 'D', 'E'):
                return 'S', 'Premium'
            else:
                return 'R', 'Regular'

        for label in submitted_labels:
            if len(label) < 2:
                continue
            row_letter = label[0].upper()
            col_str    = label[1:]
            if not col_str.isdigit():
                continue
            col = int(col_str)

            prefix, stype = js_label_to_db_prefix_and_type(label)
            if not prefix:
                continue

            if row_letter == 'A':
                db_num = col
            elif row_letter in ('B', 'C', 'D', 'E'):
                row_idx = SILVER_ROWS.index(row_letter)
                db_num  = row_idx * 16 + col
            else:
                row_idx = GENERAL_ROWS.index(row_letter) if row_letter in GENERAL_ROWS else 0
                db_num  = row_idx * 16 + col

            db_seat_number = prefix + str(db_num)

            seat = Seat.query.filter_by(
                screen_id   = show.screen_id,
                seat_number = db_seat_number
            ).first()

            if seat:
                seat.booking_id = booking_id
                seat.status     = "Booked"

        show.available_seats = max(0, (show.available_seats or 60) - num_tickets)

        # ── Release locks held by this session (seats are now confirmed) ───────
        if session_id:
            SeatLock.query.filter(
                SeatLock.show_id    == show_id,
                SeatLock.session_id == session_id,
            ).delete(synchronize_session=False)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f"Booking failed due to a server error. Please try again. ({e})", "danger")
        return redirect(url_for("user.seat_selection", show_id=show_id))

    return redirect(url_for("user.payment", booking_id=booking_id))


# ── Confirm Booking ────────────────────────────────────────────────────────────
@user_bp.route("/booking/confirm", methods=["POST"])
@login_required
def confirm_booking():
    show_id  = request.form.get("show_id")
    seat_ids = request.form.getlist("seat_ids")

    if not show_id:
        flash("Invalid request — show not found.", "danger")
        return redirect(url_for("user.movies"))

    if not seat_ids:
        flash("Please select at least one seat before booking.", "warning")
        return redirect(url_for("user.seat_selection", show_id=show_id))

    show  = Show.query.get_or_404(show_id)
    seats = Seat.query.filter(Seat.seat_id.in_(seat_ids)).all()

    if not seats:
        flash("Selected seats could not be found. Please try again.", "danger")
        return redirect(url_for("user.seat_selection", show_id=show_id))

    # ── FIX: treat NULL or empty status as "Available" ────────────────────────
    # Seeded data often leaves status as NULL.  We normalise here and book.
    for seat in seats:
        if not seat.status:
            seat.status = "Available"

    unavailable = [s for s in seats if s.status.strip().lower() != "available"]
    if unavailable:
        flash(
            f"Seat(s) {', '.join(s.seat_number for s in unavailable)} "
            f"are no longer available. Please choose different seats.",
            "danger"
        )
        return redirect(url_for("user.seat_selection", show_id=show_id))

    # ── Create booking ─────────────────────────────────────────────────────────
    booking_id = _next_booking_id()
    booking = Booking(
        booking_id     = booking_id,
        user_id        = current_user.user_id,
        show_id        = show_id,
        booking_date   = datetime.utcnow(),
        total_tickets  = len(seats),
        payment_status = "Pending",
    )
    db.session.add(booking)

    for seat in seats:
        seat.booking_id = booking_id
        seat.status     = "Booked"
        if seat.charges is None:
            seat.charges = 0.0

    show.available_seats = max(0, (show.available_seats or 0) - len(seats))
    db.session.commit()

    return redirect(url_for("user.payment", booking_id=booking_id))


# ── Payment ────────────────────────────────────────────────────────────────────
# ── Payment ────────────────────────────────────────────────────────────────────
@user_bp.route("/payment/<booking_id>", methods=["GET", "POST"])
@login_required
def payment(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.user_id:
        flash("Access denied.", "danger")
        return redirect(url_for("user.dashboard"))

    show  = booking.show
    state = _booking_state(booking)

    # ── Auto expire booking if show already started ──────────────────────────
    if state["status"] == "EXPIRED" and booking.payment_status == "Pending":

        booking.payment_status = "EXPIRED"

        booked_seats = list(booking.seats)

        for seat in booked_seats:
            seat.status = "Available"
            seat.booking_id = None

        if show:
            show.available_seats = (
                show.available_seats or 0
            ) + len(booked_seats)

        db.session.commit()

        flash(
            "This booking has expired — the show has already started.",
            "warning"
        )

        return redirect(url_for("user.my_bookings"))

    # ── Prevent payment if booking invalid ───────────────────────────────────
    if not state["can_pay"] and request.method == "GET":

        flash(
            state["cancel_blocked_reason"]
            or "Payment is not available for this booking.",
            "warning"
        )

        return redirect(url_for("user.my_bookings"))

    # ── Price Calculation ────────────────────────────────────────────────────
    seats = list(booking.seats)

    # Base ticket amount
    base_total = (
        float(show.price_per_ticket or 0)
        * booking.total_tickets
    )

    # Seat extra charges
    surcharge = sum(
        float(s.charges or 0)
        for s in seats
    )

    # Subtotal
    subtotal = base_total + surcharge

    # Convenience fee
    convenience_fee = 30

    # GST 18%
    gst = round(
        (subtotal + convenience_fee) * 0.18,
        2
    )

    # Final total
    total_amount = round(
        subtotal + convenience_fee + gst,
        2
    )

    # ── Payment Submit ───────────────────────────────────────────────────────
    if request.method == "POST":

        # Re-check payment validity
        state_post = _booking_state(booking)

        if not state_post["can_pay"]:

            flash(
                "Payment is no longer available — show may have started.",
                "danger"
            )

            return redirect(url_for("user.my_bookings"))

        method     = request.form.get("payment_method", "UPI")
        rzp_pid    = request.form.get("razorpay_payment_id", "")
        session_id = request.form.get("lock_session_id", "").strip()

        payment_id = _next_payment_id()

        pay = Payment(
            payment_id         = payment_id,
            booking_id         = booking_id,
            user_id            = current_user.user_id,
            payment_method     = method,
            payment_date       = datetime.utcnow(),
            transaction_status = "Success",
        )

        db.session.add(pay)

        booking.payment_status = "Completed"

        # Save financial data
        booking.convenience_fee = convenience_fee
        booking.total_amount    = total_amount

        # Release seat locks
        if session_id and show:

            SeatLock.query.filter(
                SeatLock.show_id == show.show_id,
                SeatLock.session_id == session_id,
            ).delete(synchronize_session=False)

        db.session.commit()

        # ── Send Confirmation Email ──────────────────────────────────────────
        try:
            from mail_utils import send_booking_confirmation

            send_booking_confirmation(
                user_name=current_user.name,
                user_email=current_user.email,
                booking={
                    "booking_id":      booking_id,
                    "movie_title":     show.movie.title,
                    "show_date":       show.show_date,
                    "start_time":      show.start_time,
                    "theater_name":    show.theater.name,
                    "theater_city":    show.theater.city,
                    "seats":           (
                        booking.seat_labels
                        or ", ".join(s.seat_number for s in seats)
                    ),
                    "base_total":      base_total,
                    "surcharge":       surcharge,
                    "convenience_fee": convenience_fee,
                    "gst":             gst,
                    "total_amount":    total_amount,
                },
            )
        except Exception as _mail_exc:
            import logging as _log
            _log.getLogger(__name__).error(
                "[BOOKING EMAIL] Failed for booking %s: %s", booking_id, _mail_exc
            )

        # ── Redirect to confirmation page ───────────────────────────────────
        return redirect(
            url_for(
                "user.booking_confirmation",
                booking_id=booking_id
            )
        )

    # ── Render Payment Page ──────────────────────────────────────────────────
    return render_template(
        "user/payment.html",
        booking=booking,
        show=show,
        seats=seats,

        base_total=base_total,
        surcharge=surcharge,
        subtotal=subtotal,
        convenience_fee=convenience_fee,
        gst=gst,

        total=total_amount
    )
# ── Booking Confirmation ───────────────────────────────────────────────────────
@user_bp.route("/booking/confirmation/<booking_id>")
@login_required
def booking_confirmation(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.user_id:
        return redirect(url_for("user.dashboard"))

    seats = list(booking.seats)
    show  = booking.show

    # Ticket price
    base = float(show.price_per_ticket or 0) * booking.total_tickets

    # Extra charges
    extra = sum(float(s.charges or 0) for s in seats)

    # Subtotal
    subtotal = base + extra

    # Convenience fee
    convenience_fee = 30

    # GST
    gst = round((subtotal + convenience_fee) * 0.18, 2)

    # Final amount
    total = round(subtotal + convenience_fee + gst, 2)

    # Seat labels
    seat_label_list = []

    if booking.seat_labels:
        seat_label_list = [
            lb.strip()
            for lb in booking.seat_labels.split(",")
            if lb.strip()
        ]

    elif seats:
        seat_label_list = [s.seat_number for s in seats]

    return render_template(
        "user/booking_confirmation.html",
        booking=booking,
        seats=seats,
        total=total,
        seat_label_list=seat_label_list
    )


# ── User Dashboard ─────────────────────────────────────────────────────────────
@user_bp.route("/dashboard")
@login_required
def dashboard():
    bookings = (Booking.query.filter_by(user_id=current_user.user_id)
                .order_by(Booking.booking_date.desc()).all())
    payments = (Payment.query.filter_by(user_id=current_user.user_id)
                .order_by(Payment.payment_date.desc()).all())
    booking_states = {b.booking_id: _booking_state(b) for b in bookings}
    return render_template("user/dashboard.html", bookings=bookings,
                           payments=payments, booking_states=booking_states)


@user_bp.route("/my-bookings")
@login_required
def my_bookings():
    bookings = (Booking.query.filter_by(user_id=current_user.user_id)
                .order_by(Booking.booking_date.desc()).all())
    booking_states = {b.booking_id: _booking_state(b) for b in bookings}
    return render_template("user/my_bookings.html", bookings=bookings,
                           booking_states=booking_states)


# ── Cancel Payment (mid-payment flow) ─────────────────────────────────────────
@user_bp.route("/payment/<booking_id>/cancel", methods=["POST"])
@login_required
def cancel_payment(booking_id):
    """
    Called when user cancels mid-payment.
    Marks booking Cancelled, releases seat locks, and frees the DB seats.
    """
    booking = Booking.query.filter_by(
        booking_id=booking_id, user_id=current_user.user_id
    ).first_or_404()

    if booking.payment_status not in (None, "Pending"):
        flash("Cannot cancel this booking at this stage.", "warning")
        return redirect(url_for("user.dashboard"))

    session_id = request.form.get("lock_session_id", "").strip()
    show       = booking.show

    # Release seat locks for this session
    if session_id and show:
        SeatLock.query.filter(
            SeatLock.show_id    == show.show_id,
            SeatLock.session_id == session_id,
        ).delete(synchronize_session=False)

    # Free booked DB seats
    booked_seats = list(booking.seats)
    for seat in booked_seats:
        seat.status     = "Available"
        seat.booking_id = None

    if show:
        show.available_seats = (show.available_seats or 0) + len(booked_seats)

    booking.payment_status = "Cancelled"
    db.session.commit()

    flash("Payment cancelled. Your seats have been released.", "info")
    return redirect(url_for("user.seat_selection", show_id=booking.show_id))


@user_bp.route("/bookings/<booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    """Cancel a confirmed booking — uses _booking_state for all validation."""
    booking = Booking.query.filter_by(
        booking_id=booking_id, user_id=current_user.user_id
    ).first_or_404()

    state = _booking_state(booking)
    show  = booking.show

    # ── Strict backend guard ─────────────────────────────────────────────────
    if not state["can_cancel"]:
        flash(state["cancel_blocked_reason"] or "Cancellation not allowed.", "danger")
        return redirect(url_for("user.my_bookings"))

    reason     = request.form.get("reason", "").strip() or "User requested cancellation"
    refund_amt = state["refund_amount"]   # already max(0, total - conv_fee)
    conv_fee   = state["conv_fee"]

    # ── Mark EXPIRED pending shows: release seats as USED not AVAILABLE ─────
    # For a valid cancellation: release seats → AVAILABLE
    booked_seats = list(booking.seats)
    for seat in booked_seats:
        seat.status     = "Available"
        seat.booking_id = None

    if show:
        show.available_seats = (show.available_seats or 0) + len(booked_seats)

    # ── Update booking ────────────────────────────────────────────────────────
    booking.payment_status      = "CANCELLED"
    booking.refund_status       = "PENDING"
    booking.cancellation_reason = reason
    booking.cancelled_at        = datetime.utcnow()
    booking.refund_amount       = refund_amt
    # Ensure total_amount is persisted for future refund calcs
    if not booking.total_amount:
        booking.total_amount = state["total_amount"]
    if not booking.convenience_fee:
        booking.convenience_fee = conv_fee

    db.session.commit()

    try:
        from mail_utils import send_cancellation_email

        send_cancellation_email(
            user_name=current_user.name,
            user_email=current_user.email,
            booking_id=booking.booking_id,
            movie_title=(show.movie.title if show and show.movie else ""),
            refund_amount=refund_amt,
            convenience_fee=conv_fee,
        )
    except Exception as _mail_exc:
        import logging as _log
        _log.getLogger(__name__).error(
            "[CANCEL EMAIL] Failed for booking %s: %s",
            booking.booking_id, _mail_exc
        )

    flash(f"Booking cancelled. Refund of ₹{refund_amt:.2f} is pending admin approval.", "success")
    return redirect(url_for("user.my_bookings"))


# ── JSON Cancel API (used by AJAX from my_bookings page) ──────────────────────
@user_bp.route("/api/bookings/<booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking_api(booking_id):
    """Cancel a confirmed booking and return JSON — used by the modal fetch()."""
    from flask import jsonify as _json

    booking = Booking.query.filter_by(
        booking_id=booking_id, user_id=current_user.user_id
    ).first()
    if not booking:
        return _json({"ok": False, "error": "Booking not found."}), 404

    state = _booking_state(booking)
    show  = booking.show

    # ── Guard: already cancelled / duplicate request ──────────────────────────
    ps = state["status"]
    if ps in ("CANCELLED", "REFUNDED"):
        return _json({"ok": False, "error": "This booking is already cancelled."}), 409
    if ps == "EXPIRED":
        return _json({"ok": False, "error": "This booking has expired — cancellation not possible."}), 409

    if not state["can_cancel"]:
        reason_msg = state["cancel_blocked_reason"] or "Cancellation not allowed."
        return _json({"ok": False, "error": reason_msg}), 422

    # ── Parse reason from JSON body or form data ──────────────────────────────
    data       = request.get_json(silent=True) or {}
    reason     = (data.get("reason") or request.form.get("reason") or "").strip()
    reason     = reason or "User requested cancellation"

    refund_amt = state["refund_amount"]   # already max(0, total - conv_fee)
    conv_fee   = state["conv_fee"]
    total_amt  = state["total_amount"]

    # ── Release seats → Available ─────────────────────────────────────────────
    booked_seats = list(booking.seats)
    for seat in booked_seats:
        seat.status     = "Available"
        seat.booking_id = None

    if show:
        show.available_seats = (show.available_seats or 0) + len(booked_seats)

    # ── Update booking record ─────────────────────────────────────────────────
    booking.payment_status      = "CANCELLED"
    booking.refund_status       = "PENDING"
    booking.cancellation_reason = reason
    booking.cancelled_at        = datetime.utcnow()
    booking.refund_amount       = refund_amt
    if not booking.total_amount:
        booking.total_amount = total_amt
    if not booking.convenience_fee:
        booking.convenience_fee = conv_fee

    db.session.commit()

    # ── Fire cancellation email (best-effort) ─────────────────────────────────
    try:
        from mail_utils import send_cancellation_email

        send_cancellation_email(
            user_name=current_user.name,
            user_email=current_user.email,
            booking_id=booking.booking_id,
            movie_title=(show.movie.title if show and show.movie else ""),
            refund_amount=refund_amt,
            convenience_fee=conv_fee,
        )
    except Exception as _mail_exc:
        import logging as _log
        _log.getLogger(__name__).error(
            "[CANCEL EMAIL] Failed for booking %s: %s",
            booking.booking_id, _mail_exc
        )

    return _json({
        "ok":           True,
        "booking_id":   booking_id,
        "refund_amount": round(refund_amt, 2),
        "conv_fee":      round(conv_fee, 2),
        "total_amount":  round(total_amt, 2),
        "message":      f"Booking cancelled. Refund of ₹{refund_amt:.2f} is pending admin approval.",
    })


# ── Contact ────────────────────────────────────────────────────────────────────
@user_bp.route("/contact", methods=["GET", "POST"])
def contact():
    from models.message_model import Message
    if request.method == "POST":
        name    = request.form.get("name",    "").strip()
        email   = request.form.get("email",   "").strip().lower()
        subject = request.form.get("subject", "").strip()
        body    = request.form.get("message", "").strip()
        if not name or not email or not body:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("user.contact"))
        from models.message_model import Message
        db.session.add(Message(name=name, email=email,
                               subject=subject or "(no subject)", body=body))
        db.session.commit()
        flash("Thanks for reaching out! We'll get back to you shortly. 🎬", "success")
        return redirect(url_for("user.contact"))
    return render_template("user/contact.html")


@user_bp.route("/about")
def about():
    from models.movie_model import Movie
    from models.theater_model import Theater
    from models.booking_model import Booking
    from models.user_model import User
    stats = {
        "movies": Movie.query.count(),
        "theaters": Theater.query.count(),
        "bookings": Booking.query.count(),
        "users": User.query.filter_by(role="user").count(),
    }
    return render_template("user/about.html", stats=stats)

# ── Booking state API (used by my_bookings JS) ────────────────────────────────
@user_bp.route("/api/booking/<booking_id>/state")
@login_required
def booking_state_api(booking_id):
    """Returns live state of a booking — used by frontend to update UI."""
    booking = Booking.query.filter_by(
        booking_id=booking_id, user_id=current_user.user_id
    ).first_or_404()

    state = _booking_state(booking)

    # Persist auto-EXPIRED status to DB
    if state['status'] == 'EXPIRED' and (booking.payment_status or '').strip() == 'Pending':
        booking.payment_status = 'EXPIRED'
        booked_seats = list(booking.seats)
        for seat in booked_seats:
            seat.status     = 'Available'
            seat.booking_id = None
        show = booking.show
        if show:
            show.available_seats = (show.available_seats or 0) + len(booked_seats)
        db.session.commit()

    return jsonify({
        'booking_id':             booking_id,
        'status':                 state['status'],
        'show_expired':           state['show_expired'],
        'can_pay':                state['can_pay'],
        'can_cancel':             state['can_cancel'],
        'cancel_blocked_reason':  state['cancel_blocked_reason'],
        'refund_amount':          state['refund_amount'],
        'conv_fee':               state['conv_fee'],
        'total_amount':           state['total_amount'],
    })
