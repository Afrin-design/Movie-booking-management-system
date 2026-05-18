"""
routes/admin_analytics.py
─────────────────────────
Admin Analytics — 100% dynamic from DB via SQLAlchemy + AJAX JSON APIs.
Mounted at /admin/analytics via app.py.
"""

from flask import Blueprint, render_template, jsonify, abort
from flask_login import login_required, current_user
from database.db import db
from models.movie_model   import Movie
from models.theater_model import Theater
from models.show_model    import Show
from models.booking_model import Booking
from models.payment_model import Payment
from models.user_model    import User
from models.seats_model   import Seat
from models.screen_model  import Screen
from functools import wraps
import sqlalchemy as sa
from datetime import datetime, timedelta
import calendar

admin_analytics_bp = Blueprint("admin_analytics", __name__)


# ── Guards & Helpers ─────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _safe(val, default=0, cast=int):
    try:
        return cast(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _revenue_expr():
    """SQLAlchemy expression: SUM(price_per_ticket * total_tickets)."""
    return sa.func.coalesce(
        sa.func.sum(
            sa.cast(Show.price_per_ticket, sa.Numeric) * Booking.total_tickets
        ), 0
    )


# ── Shared query builder ──────────────────────────────────────────────────────

def _paid_base():
    """Base query joining Payment→Booking→Show, filtered to Success."""
    return (db.session.query()
            .select_from(Payment)
            .join(Booking, Booking.booking_id == Payment.booking_id)
            .join(Show,    Show.show_id       == Booking.show_id)
            .filter(Payment.transaction_status == "Success"))


# ═══════════════════════════════════════════════════════════════════════════════
#  KPIs — computed once and shared between page + API
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_kpis():
    total_revenue = (
        db.session.query(_revenue_expr())
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .filter(Payment.transaction_status == "Success")
        .scalar() or 0
    )
    total_bookings      = Booking.query.count()
    successful_bookings = (
        Booking.query.join(Booking.payments)
        .filter(Payment.transaction_status == "Success")
        .distinct(Booking.booking_id).count()
    )
    total_users    = User.query.filter_by(role="user").count()
    total_theaters = Theater.query.count()
    total_movies   = Movie.query.count()
    avg_ticket     = (float(total_revenue) / successful_bookings
                      if successful_bookings else 0)
    return dict(
        total_revenue       = float(total_revenue),
        total_bookings      = total_bookings,
        successful_bookings = successful_bookings,
        total_users         = total_users,
        total_theaters      = total_theaters,
        total_movies        = total_movies,
        avg_ticket_value    = round(avg_ticket, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Individual data builders (used by both page render & AJAX)
# ═══════════════════════════════════════════════════════════════════════════════

def _monthly_trend():
    rows = (
        db.session.query(
            sa.func.extract("year",  Booking.booking_date).label("yr"),
            sa.func.extract("month", Booking.booking_date).label("mo"),
            _revenue_expr().label("revenue"),
            sa.func.count(Booking.booking_id).label("cnt"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .filter(
            Payment.transaction_status == "Success",
            Booking.booking_date >= datetime.now() - timedelta(days=365),
            Booking.booking_date.isnot(None),
        )
        .group_by("yr", "mo").order_by("yr", "mo").all()
    )
    labels, revenue, counts = [], [], []
    for r in rows:
        mo, yr = _safe(r.mo), _safe(r.yr)
        if not (1 <= mo <= 12) or yr == 0:
            continue
        labels.append(f"{calendar.month_abbr[mo]} {yr}")
        revenue.append(float(r.revenue))
        counts.append(_safe(r.cnt))
    return {"labels": labels, "revenue": revenue, "counts": counts}


def _genre_breakdown():
    rows = (
        db.session.query(
            Movie.genre,
            _revenue_expr().label("revenue"),
            sa.func.count(Booking.booking_id).label("cnt"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Movie,   Movie.movie_id     == Show.movie_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Movie.genre)
        .order_by(sa.desc("revenue")).limit(8).all()
    )
    return {
        "labels":  [r.genre or "Unknown" for r in rows],
        "revenue": [float(r.revenue)     for r in rows],
        "counts":  [_safe(r.cnt)         for r in rows],
    }


def _top_movies():
    rows = (
        db.session.query(
            Movie.title,
            _revenue_expr().label("revenue"),
            sa.func.sum(Booking.total_tickets).label("tickets"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Movie,   Movie.movie_id     == Show.movie_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Movie.title)
        .order_by(sa.desc("revenue")).limit(10).all()
    )
    return {
        "labels":  [r.title          for r in rows],
        "revenue": [float(r.revenue) for r in rows],
        "tickets": [_safe(r.tickets) for r in rows],
    }


def _top_theaters():
    rows = (
        db.session.query(
            Theater.name, Theater.city,
            _revenue_expr().label("revenue"),
            sa.func.count(Booking.booking_id).label("bookings"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Theater.theater_id, Theater.name, Theater.city)
        .order_by(sa.desc("revenue")).limit(10).all()
    )
    return {
        "labels":   [f"{r.name} ({r.city or ''})" for r in rows],
        "revenue":  [float(r.revenue)              for r in rows],
        "bookings": [_safe(r.bookings)             for r in rows],
    }


def _city_breakdown():
    rows = (
        db.session.query(
            Theater.city,
            _revenue_expr().label("revenue"),
            sa.func.count(Booking.booking_id).label("cnt"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Theater.city)
        .order_by(sa.desc("revenue")).limit(10).all()
    )
    return {
        "labels":  [r.city or "Unknown" for r in rows],
        "revenue": [float(r.revenue)    for r in rows],
        "counts":  [_safe(r.cnt)        for r in rows],
    }


def _payment_methods():
    rows = (
        db.session.query(
            Payment.payment_method,
            sa.func.count(Payment.payment_id).label("cnt"),
            _revenue_expr().label("revenue"),
        )
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Payment.payment_method)
        .order_by(sa.desc("cnt")).all()
    )
    return {
        "labels":  [r.payment_method for r in rows if r.payment_method],
        "counts":  [_safe(r.cnt)      for r in rows if r.payment_method],
        "revenue": [float(r.revenue)  for r in rows if r.payment_method],
    }


def _booking_status():
    rows = (
        db.session.query(
            Payment.transaction_status,
            sa.func.count(Payment.payment_id).label("cnt"),
        )
        .group_by(Payment.transaction_status).all()
    )
    return {
        "labels": [r.transaction_status or "Unknown" for r in rows],
        "counts": [_safe(r.cnt)                      for r in rows],
    }


def _dow_heatmap():
    rows = (
        db.session.query(
            sa.func.extract("dow", Booking.booking_date).label("dow"),
            sa.func.count(Booking.booking_id).label("cnt"),
            _revenue_expr().label("revenue"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .filter(
            Payment.transaction_status == "Success",
            Booking.booking_date.isnot(None),
        )
        .group_by("dow").order_by("dow").all()
    )
    dow_map = {_safe(r.dow): (_safe(r.cnt), float(r.revenue)) for r in rows}
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    return {
        "labels":  day_names,
        "counts":  [dow_map.get(i, (0, 0))[0] for i in range(7)],
        "revenue": [dow_map.get(i, (0, 0))[1] for i in range(7)],
    }


def _language_breakdown():
    rows = (
        db.session.query(
            Movie.language,
            _revenue_expr().label("revenue"),
            sa.func.count(Booking.booking_id).label("cnt"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Movie,   Movie.movie_id     == Show.movie_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Movie.language)
        .order_by(sa.desc("revenue")).all()
    )
    return {
        "labels":  [r.language or "Unknown" for r in rows],
        "revenue": [float(r.revenue)        for r in rows],
        "counts":  [_safe(r.cnt)            for r in rows],
    }


def _seat_type_breakdown():
    rows = (
        db.session.query(
            Seat.seat_type,
            sa.func.count(Seat.seat_id).label("cnt"),
            sa.func.coalesce(
                sa.func.sum(sa.cast(Seat.charges, sa.Numeric)), 0
            ).label("charges"),
        )
        .filter(Seat.status == "Booked", Seat.seat_type.isnot(None))
        .group_by(Seat.seat_type)
        .order_by(sa.desc("cnt")).all()
    )
    return {
        "labels":  [r.seat_type or "Unknown" for r in rows],
        "counts":  [_safe(r.cnt)             for r in rows],
        "charges": [float(r.charges)         for r in rows],
    }


def _active_users_monthly():
    rows = (
        db.session.query(
            sa.func.extract("year",  Booking.booking_date).label("yr"),
            sa.func.extract("month", Booking.booking_date).label("mo"),
            sa.func.count(sa.distinct(Booking.user_id)).label("unique_users"),
        )
        .filter(
            Booking.booking_date.isnot(None),
            Booking.booking_date >= datetime.now() - timedelta(days=365),
        )
        .group_by("yr", "mo").order_by("yr", "mo").all()
    )
    labels, counts = [], []
    for r in rows:
        mo, yr = _safe(r.mo), _safe(r.yr)
        if not (1 <= mo <= 12) or yr == 0:
            continue
        labels.append(f"{calendar.month_abbr[mo]} {yr}")
        counts.append(_safe(r.unique_users))
    return {"labels": labels, "counts": counts}


def _occupancy():
    """Overall seat occupancy: booked / total seats."""
    total  = db.session.query(sa.func.count(Seat.seat_id)).scalar() or 0
    booked = (db.session.query(sa.func.count(Seat.seat_id))
              .filter(Seat.status == "Booked").scalar() or 0)
    pct    = round(booked / total * 100, 1) if total else 0
    return {"total": total, "booked": booked, "pct": pct}


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN PAGE ROUTE
# ═══════════════════════════════════════════════════════════════════════════════

@admin_analytics_bp.route("/")
@admin_required
def analytics():
    """Returns instantly — all heavy data loaded via AJAX after page load."""
    return render_template("admin/analytics.html",
        # KPIs — empty defaults, filled by AJAX
        total_revenue=0, total_bookings=0, total_movies=0, total_theaters=0,
        total_users=0, avg_ticket_price=0,
        genre_revenue        = [],
        monthly_labels       = [], monthly_revenue      = [], monthly_counts       = [],
        top_movie_labels     = [], top_movie_revenue    = [], top_movie_tickets    = [],
        top_theater_labels   = [], top_theater_revenue  = [], top_theater_bookings = [],
        city_labels          = [], city_revenue         = [], city_counts          = [],
        pay_labels           = [], pay_counts           = [], pay_revenue          = [],
        status_labels        = [], status_counts        = [],
        dow_labels           = [], dow_counts           = [], dow_revenue          = [],
        lang_labels          = [], lang_revenue         = [], lang_counts          = [],
        seat_type_labels     = [], seat_type_counts     = [], seat_type_charges    = [],
        user_month_labels    = [], user_month_counts    = [],
        occ_total=0, occ_booked=0, occ_pct=0,
        brands=[], total_brand_rev=1,
        brand_labels=[], brand_revenue=[], brand_bookings=[],
    )

# ═══════════════════════════════════════════════════════════════════════════════
#  AJAX API ENDPOINTS — all return fresh DB data as JSON
# ═══════════════════════════════════════════════════════════════════════════════

@admin_analytics_bp.route("/api/kpis")
@admin_required
def api_kpis():
    return jsonify(_compute_kpis())


@admin_analytics_bp.route("/api/monthly")
@admin_required
def api_monthly():
    return jsonify(_monthly_trend())


@admin_analytics_bp.route("/api/genre")
@admin_required
def api_genre():
    return jsonify(_genre_breakdown())


@admin_analytics_bp.route("/api/movies")
@admin_required
def api_movies():
    return jsonify(_top_movies())


@admin_analytics_bp.route("/api/theaters")
@admin_required
def api_theaters():
    return jsonify(_top_theaters())


@admin_analytics_bp.route("/api/city")
@admin_required
def api_city():
    return jsonify(_city_breakdown())


@admin_analytics_bp.route("/api/payments")
@admin_required
def api_payments():
    return jsonify(_payment_methods())


@admin_analytics_bp.route("/api/status")
@admin_required
def api_status():
    return jsonify(_booking_status())


@admin_analytics_bp.route("/api/dow")
@admin_required
def api_dow():
    return jsonify(_dow_heatmap())


@admin_analytics_bp.route("/api/language")
@admin_required
def api_language():
    return jsonify(_language_breakdown())


@admin_analytics_bp.route("/api/seats")
@admin_required
def api_seats():
    return jsonify(_seat_type_breakdown())


@admin_analytics_bp.route("/api/users-monthly")
@admin_required
def api_users_monthly():
    return jsonify(_active_users_monthly())


@admin_analytics_bp.route("/api/occupancy")
@admin_required
def api_occupancy():
    return jsonify(_occupancy())


@admin_analytics_bp.route("/api/all")
@admin_required
def api_all():
    """Single endpoint returning all analytics data — used for auto-refresh."""
    def safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default or {}
    return jsonify({
        "kpis":      safe(_compute_kpis),
        "monthly":   safe(_monthly_trend),
        "genre":     safe(_genre_breakdown),
        "movies":    safe(_top_movies),
        "theaters":  safe(_top_theaters),
        "city":      safe(_city_breakdown),
        "payments":  safe(_payment_methods),
        "status":    safe(_booking_status),
        "dow":       safe(_dow_heatmap),
        "language":  safe(_language_breakdown),
        "seats":     safe(_seat_type_breakdown),
        "users_mo":  safe(_active_users_monthly),
        "occupancy": safe(_occupancy),
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  EXTENDED API ENDPOINTS — for the new professional analytics dashboard
# ═══════════════════════════════════════════════════════════════════════════════

def _daily_trend(days=90):
    """Bookings per day for last N days."""
    rows = (
        db.session.query(
            sa.func.date(Booking.booking_date).label("day"),
            sa.func.count(Booking.booking_id).label("cnt"),
            _revenue_expr().label("revenue"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .filter(
            Payment.transaction_status == "Success",
            Booking.booking_date >= datetime.now() - timedelta(days=days),
            Booking.booking_date.isnot(None),
        )
        .group_by(sa.func.date(Booking.booking_date))
        .order_by("day").all()
    )
    return {
        "labels":  [str(r.day) for r in rows],
        "counts":  [_safe(r.cnt) for r in rows],
        "revenue": [float(r.revenue) for r in rows],
    }


def _time_slot_breakdown():
    """Bookings by time slot using show start_time."""
    slots = {"Morning(6-12)": 0, "Afternoon(12-17)": 0,
             "Evening(17-21)": 0, "Night(21-24)": 0}
    rows = (
        db.session.query(
            sa.func.substr(Show.start_time, 1, 2).label("hr"),
            sa.func.count(Booking.booking_id).label("cnt"),
            _revenue_expr().label("revenue"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .filter(
            Payment.transaction_status == "Success",
            Show.start_time.isnot(None),
        )
        .group_by("hr").all()
    )
    rev = {"Morning(6-12)": 0, "Afternoon(12-17)": 0,
           "Evening(17-21)": 0, "Night(21-24)": 0}
    for r in rows:
        try:
            h = int(str(r.hr).strip())
        except (ValueError, TypeError):
            continue
        if 6 <= h < 12:   key = "Morning(6-12)"
        elif 12 <= h < 17: key = "Afternoon(12-17)"
        elif 17 <= h < 21: key = "Evening(17-21)"
        else:               key = "Night(21-24)"
        slots[key] += _safe(r.cnt)
        rev[key]   += float(r.revenue)
    return {
        "labels":  list(slots.keys()),
        "counts":  list(slots.values()),
        "revenue": list(rev.values()),
    }


def _ratings_vs_bookings():
    """Scatter data: movie rating vs total bookings."""
    rows = (
        db.session.query(
            Movie.title, Movie.rating,
            sa.func.count(Booking.booking_id).label("cnt"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Movie,   Movie.movie_id     == Show.movie_id)
        .filter(
            Payment.transaction_status == "Success",
            Movie.rating.isnot(None),
        )
        .group_by(Movie.movie_id, Movie.title, Movie.rating).all()
    )
    return {
        "points": [
            {"x": float(r.rating or 0), "y": _safe(r.cnt), "label": r.title}
            for r in rows if r.rating
        ]
    }


def _screen_type_performance():
    """Bookings & revenue by seat type (Gold/Silver/General) since Screen has no screen_type."""
    rows = (
        db.session.query(
            Seat.seat_type,
            sa.func.count(sa.distinct(Booking.booking_id)).label("cnt"),
            sa.func.coalesce(sa.func.sum(
                sa.cast(Show.price_per_ticket, sa.Numeric) * Booking.total_tickets
            ), 0).label("revenue"),
        )
        .select_from(Seat)
        .join(Booking, Booking.booking_id == Seat.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Payment, Payment.booking_id == Booking.booking_id)
        .filter(
            Payment.transaction_status == "Success",
            Seat.seat_type.isnot(None),
        )
        .group_by(Seat.seat_type)
        .order_by(sa.desc("cnt")).all()
    )
    if not rows:
        # Fallback: use screen seat layout counts
        rows2 = (
            db.session.query(
                sa.literal("Gold").label("seat_type"),
                sa.func.sum(Screen.gold_seats).label("cnt"),
            ).select_from(Screen).all()
        )
    return {
        "labels":  [r.seat_type or "Standard" for r in rows],
        "counts":  [_safe(r.cnt)              for r in rows],
        "revenue": [float(r.revenue)          for r in rows],
    }


def _grouped_theater_by_city():
    """Grouped bar: top theaters grouped by city."""
    rows = (
        db.session.query(
            Theater.city,
            Theater.name,
            sa.func.count(Booking.booking_id).label("cnt"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Theater.city, Theater.theater_id, Theater.name)
        .order_by(sa.desc("cnt")).limit(20).all()
    )
    # Build city→theaters dict
    from collections import defaultdict
    city_map = defaultdict(list)
    for r in rows:
        city_map[r.city].append({"name": r.name, "cnt": _safe(r.cnt)})
    return {"cities": dict(city_map)}


def _multi_movie_trend():
    """Top 5 movies daily bookings for multi-line chart."""
    # get top 5 movie IDs by bookings
    top5 = (
        db.session.query(Movie.movie_id, Movie.title,
                         sa.func.count(Booking.booking_id).label("total"))
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Movie,   Movie.movie_id     == Show.movie_id)
        .filter(Payment.transaction_status == "Success")
        .group_by(Movie.movie_id, Movie.title)
        .order_by(sa.desc("total")).limit(5).all()
    )
    result = {"movies": []}
    for m in top5:
        rows = (
            db.session.query(
                sa.func.date(Booking.booking_date).label("day"),
                sa.func.count(Booking.booking_id).label("cnt"),
            )
            .select_from(Payment)
            .join(Booking, Booking.booking_id == Payment.booking_id)
            .join(Show,    Show.show_id       == Booking.show_id)
            .filter(
                Payment.transaction_status == "Success",
                Show.movie_id == m.movie_id,
                Booking.booking_date >= datetime.now() - timedelta(days=60),
                Booking.booking_date.isnot(None),
            )
            .group_by(sa.func.date(Booking.booking_date))
            .order_by("day").all()
        )
        result["movies"].append({
            "title":  m.title,
            "labels": [str(r.day)   for r in rows],
            "data":   [_safe(r.cnt) for r in rows],
        })
    return result


@admin_analytics_bp.route("/api/daily")
@admin_required
def api_daily():
    days = 90
    return jsonify(_daily_trend(days))


@admin_analytics_bp.route("/api/timeslot")
@admin_required
def api_timeslot():
    return jsonify(_time_slot_breakdown())


@admin_analytics_bp.route("/api/scatter")
@admin_required
def api_scatter():
    return jsonify(_ratings_vs_bookings())


@admin_analytics_bp.route("/api/screentype")
@admin_required
def api_screentype():
    return jsonify(_screen_type_performance())


@admin_analytics_bp.route("/api/city-grouped")
@admin_required
def api_city_grouped():
    return jsonify(_grouped_theater_by_city())


@admin_analytics_bp.route("/api/multi-movie")
@admin_required
def api_multi_movie():
    return jsonify(_multi_movie_trend())


@admin_analytics_bp.route("/api/extended")
@admin_required
def api_extended():
    def safe(fn, default=None):
        try:
            return fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            return default or {}
    return jsonify({
        "daily":       safe(lambda: _daily_trend(90)),
        "timeslot":    safe(_time_slot_breakdown),
        "screentype":  safe(_screen_type_performance),
        "scatter":     safe(_ratings_vs_bookings),
        "multi_movie": safe(_multi_movie_trend),
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  BRAND ANALYTICS  (added: brand-owner mapping system)
# ═══════════════════════════════════════════════════════════════════════════════

from models.brand_model import TheaterBrand
from models.user_model  import User


def _brand_analytics():
    """
    Per-brand: revenue, bookings, theater_count, avg_ticket,
    top_city, owner_name, occupancy %.
    Optimised with a single pass using subqueries.
    """
    # Revenue + bookings per brand via theaters
    rev_sq = (
        db.session.query(
            Theater.brand_id.label("brand_id"),
            sa.func.coalesce(
                sa.func.sum(
                    sa.cast(Show.price_per_ticket, sa.Numeric)
                    * Booking.total_tickets
                ), 0
            ).label("revenue"),
            sa.func.count(sa.distinct(Booking.booking_id)).label("bookings"),
            sa.func.coalesce(
                sa.func.sum(Booking.total_tickets), 0
            ).label("tickets"),
        )
        .select_from(Payment)
        .join(Booking, Booking.booking_id == Payment.booking_id)
        .join(Show,    Show.show_id       == Booking.show_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(Payment.transaction_status == "Success",
                Theater.brand_id.isnot(None))
        .group_by(Theater.brand_id)
        .subquery()
    )

    # Theater count per brand
    tc_sq = (
        db.session.query(
            Theater.brand_id.label("brand_id"),
            sa.func.count(Theater.theater_id).label("theater_count"),
        )
        .filter(Theater.brand_id.isnot(None))
        .group_by(Theater.brand_id)
        .subquery()
    )

    # Top city per brand (city with most theaters)
    city_inner = (
        db.session.query(
            Theater.brand_id.label("bid"),
            Theater.city.label("city"),
            sa.func.count(Theater.theater_id).label("cnt"),
            sa.func.rank().over(
                partition_by=Theater.brand_id,
                order_by=sa.desc(sa.func.count(Theater.theater_id))
            ).label("rn"),
        )
        .filter(Theater.brand_id.isnot(None), Theater.city.isnot(None))
        .group_by(Theater.brand_id, Theater.city)
        .subquery()
    )
    top_city_sq = (
        db.session.query(
            city_inner.c.bid,
            city_inner.c.city,
        )
        .filter(city_inner.c.rn == 1)
        .subquery()
    )

    # Owner per brand
    owner_sq = (
        db.session.query(
            User.brand_id.label("brand_id"),
            User.name.label("owner_name"),
        )
        .filter(User.role == "theater_owner", User.brand_id.isnot(None))
        .subquery()
    )

    rows = (
        db.session.query(
            TheaterBrand.id,
            TheaterBrand.brand_name,
            TheaterBrand.status,
            sa.func.coalesce(tc_sq.c.theater_count, 0).label("theater_count"),
            sa.func.coalesce(rev_sq.c.revenue,       0).label("revenue"),
            sa.func.coalesce(rev_sq.c.bookings,      0).label("bookings"),
            sa.func.coalesce(rev_sq.c.tickets,        0).label("tickets"),
            top_city_sq.c.city.label("top_city"),
            owner_sq.c.owner_name.label("owner_name"),
        )
        .outerjoin(tc_sq,      tc_sq.c.brand_id      == TheaterBrand.id)
        .outerjoin(rev_sq,     rev_sq.c.brand_id      == TheaterBrand.id)
        .outerjoin(top_city_sq, top_city_sq.c.bid     == TheaterBrand.id)
        .outerjoin(owner_sq,   owner_sq.c.brand_id    == TheaterBrand.id)
        .order_by(sa.desc("revenue"))
        .all()
    )

    seen_names = set()
    deduped = []
    for r in rows:
        if r.brand_name not in seen_names:
            seen_names.add(r.brand_name)
            deduped.append(r)

    total_revenue = sum(float(r.revenue) for r in deduped) or 1  # avoid /0

    result = []
    for r in deduped:
        rev   = float(r.revenue)
        books = _safe(r.bookings)
        tcks  = _safe(r.tickets)
        avg_t = round(rev / books, 2) if books else 0
        share = round(rev / total_revenue * 100, 1)
        result.append({
            "id":            r.id,
            "brand_name":    r.brand_name,
            "status":        r.status,
            "theater_count": _safe(r.theater_count),
            "revenue":       rev,
            "bookings":      books,
            "tickets":       tcks,
            "avg_ticket":    avg_t,
            "revenue_share": share,
            "top_city":      r.top_city or "—",
            "owner_name":    r.owner_name or "Unassigned",
        })
    return result


@admin_analytics_bp.route("/brands")
@admin_required
def brand_analytics():
    data = _brand_analytics()

    # Totals for header KPIs
    total_rev   = sum(d["revenue"]   for d in data)
    total_books = sum(d["bookings"]  for d in data)
    total_th    = sum(d["theater_count"] for d in data)

    return render_template(
        "admin/brand_analytics.html",
        brands       = data,
        total_rev    = total_rev,
        total_books  = total_books,
        total_th     = total_th,
    )


@admin_analytics_bp.route("/api/brand-analytics")
@admin_required
def api_brand_analytics():
    data = _brand_analytics()
    return jsonify({"brands": data, "total": len(data)})

