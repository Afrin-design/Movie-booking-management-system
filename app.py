from flask import Flask, render_template
from database.db import db
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_mail import Mail
from config import config_map
import os
from datetime import datetime, date as _date_type, time as _time_type

migrate       = Migrate()
login_manager = LoginManager()
mail          = Mail()   # ← single, global Mail instance — routes import THIS object

login_manager.login_view             = "auth.login"
login_manager.login_message_category = "warning"


def _safe_strftime(value, fmt):
    """
    Jinja2 filter: formats date/time/datetime objects OR date/time strings.
    Usage in templates:  {{ s.show_date | strftime('%d %b %Y') }}
    Falls back to '—' on any error so pages never crash.
    """
    if value is None:
        return "—"
    # Already a proper date/datetime/time object
    if isinstance(value, (datetime, _date_type, _time_type)):
        return value.strftime(fmt)
    # It's a string — try common formats
    s = str(value).strip()
    for date_fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
                     "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, date_fmt).strftime(fmt)
        except ValueError:
            pass
    # Try as time string (HH:MM or HH:MM:SS)
    for time_fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, time_fmt).strftime(fmt)
        except ValueError:
            pass
    return s  # Return raw string if nothing matches

migrate       = Migrate()
login_manager = LoginManager()
mail          = Mail()   # ← single, global Mail instance — routes import THIS object

login_manager.login_view             = "auth.login"
login_manager.login_message_category = "warning"


def create_app(env=None):
    app = Flask(__name__)
    env = env or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_map[env])

    # ── Register safe strftime Jinja2 filter ─────────────────────────────────
    # This replaces the built-in .strftime() method call in templates.
    # All existing {{ value.strftime('%d %b') }} calls are also safe because
    # SQLAlchemy returns real date objects most of the time; the filter is the
    # fallback for when they come back as strings (SQLite quirk).
    app.jinja_env.filters["strftime"] = _safe_strftime


    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)          # ← configure the global mail object

    with app.app_context():
        # ── Import all models so SQLAlchemy sees them before create_all() ──
        from models.brand_model    import TheaterBrand   # brand-owner mapping
        from models.user_model     import User
        from models.movie_model    import Movie
        from models.theater_model  import Theater
        from models.screen_model   import Screen
        from models.show_model     import Show
        from models.booking_model  import Booking
        from models.payment_model  import Payment
        from models.seats_model    import Seat
        from models.reviews_model  import Review
        from models.message_model  import Message   # ← [Task 5] NEW
        from models.carousel_model import CarouselSlide  # ← Carousel
        from models.seat_lock_model import SeatLock      # ← Real-time seat locking

        db.create_all()

        # ── Safe migration: add cancellation/refund columns to bookings ─────────────
        # Uses inspector to check first — works on both PostgreSQL and SQLite.
        try:
            import sqlalchemy as _sa
            _inspector = _sa.inspect(db.engine)
            _existing_cols = {c["name"] for c in _inspector.get_columns("bookings")}

            # Detect dialect so we use the right type names
            _is_pg = db.engine.dialect.name == "postgresql"

            _new_cols = [
                ("total_amount",        "NUMERIC(10,2)"),
                ("convenience_fee",     "NUMERIC(10,2)"),
                ("refund_amount",       "NUMERIC(10,2)"),
                ("cancellation_reason", "TEXT"),
                ("cancelled_at",        "TIMESTAMP" if _is_pg else "DATETIME"),
                ("refund_status",       "VARCHAR(30)"),
            ]
            for _col_name, _col_type in _new_cols:
                if _col_name not in _existing_cols:
                    db.session.execute(db.text(
                        f"ALTER TABLE bookings ADD COLUMN {_col_name} {_col_type}"
                    ))
                    db.session.commit()
        except Exception as _mig_err:
            db.session.rollback()
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Refund column migration warning: %s", _mig_err
            )

        # ── Safe migration: add 'status' column to theaters if missing ───────
        try:
            db.session.execute(db.text(
                "ALTER TABLE theaters ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'Active'"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()  # Column already exists — ignore

        # ── Safe migration: add 'seat_labels' column to bookings ─────────────
        try:
            db.session.execute(db.text(
                "ALTER TABLE bookings ADD COLUMN seat_labels TEXT"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()  # Column already exists — ignore

        # ── Safe migration: create seat_locks table if not yet created ────────
        # db.create_all() above handles new installs; this catches existing DBs
        # that were created before seat_locks was added to the models.
        try:
            db.session.execute(db.text("""
                CREATE TABLE IF NOT EXISTS seat_locks (
                    lock_id    VARCHAR(40)  PRIMARY KEY,
                    show_id    VARCHAR(20)  NOT NULL REFERENCES shows(show_id) ON DELETE CASCADE,
                    seat_label VARCHAR(20)  NOT NULL,
                    user_id    VARCHAR(20)  REFERENCES users(user_id) ON DELETE CASCADE,
                    session_id VARCHAR(120) NOT NULL,
                    locked_at  DATETIME     NOT NULL,
                    expires_at DATETIME     NOT NULL,
                    UNIQUE(show_id, seat_label)
                )
            """))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # ── Backfill: sync brand_id on theaters where owner_id is set but ────
        # ── brand_id is NULL. This fixes theaters assigned before brand sync. ─
        try:
            from models.theater_model import Theater
            from models.user_model    import User
            orphaned = Theater.query.filter(
                Theater.owner_id.isnot(None),
                Theater.brand_id.is_(None),
            ).all()
            for t in orphaned:
                owner = User.query.get(t.owner_id)
                if owner and owner.brand_id:
                    t.brand_id = owner.brand_id
                    print(f"[MIGRATE backfill] theater {t.theater_id}: brand_id set to {owner.brand_id}")
            if orphaned:
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[MIGRATE backfill] error: {e}")

        # FIX: explicit str() cast so Flask-Login handles string PKs correctly
        @login_manager.user_loader
        def load_user(user_id):
            return User.query.get(str(user_id))

        _seed_admin(User)

        # ── Register blueprints ──────────────────────────────────────────────
        from routes.auth             import auth_bp
        from routes.user             import user_bp
        from routes.admin            import admin_bp
        from routes.theater_owner    import owner_bp
        from routes.theater_owners   import theater_owners_bp
        from routes.admin_analytics  import admin_analytics_bp
        from routes.owner_analytics  import owner_analytics_bp

        app.register_blueprint(auth_bp,             url_prefix="/auth")
        app.register_blueprint(user_bp,             url_prefix="/")
        app.register_blueprint(admin_bp,            url_prefix="/admin")
        app.register_blueprint(owner_bp,            url_prefix="/owner")
        app.register_blueprint(admin_analytics_bp,  url_prefix="/admin/analytics")
        app.register_blueprint(theater_owners_bp,   url_prefix="/admin")
        app.register_blueprint(owner_analytics_bp,  url_prefix="/owner/analytics")

        # ── Error handlers ───────────────────────────────────────────────────
        @app.errorhandler(403)
        def forbidden(e):
            return render_template("errors/403.html"), 403

        @app.errorhandler(404)
        def not_found(e):
            return render_template("errors/404.html"), 404

    # ── [Task 5] Context processor: injects `unread_messages` into every     ──
    # ── admin template so the sidebar badge stays live on ALL admin pages.   ──
    @app.context_processor
    def inject_unread_messages():
        """
        Makes `unread_messages` and `pending_refunds_count` available in every
        admin template so sidebar badges stay live on ALL admin pages.
        """
        try:
            if current_user.is_authenticated and current_user.role == "admin":
                from models.message_model import Message
                from models.booking_model import Booking
                count = Message.query.filter_by(is_read=False).count()
                pending_refunds = Booking.query.filter(
                    Booking.refund_status == "PENDING"
                ).count()
                return {"unread_messages": count, "pending_refunds_count": pending_refunds}
        except Exception:
            pass
        return {"unread_messages": 0, "pending_refunds_count": 0}

    @app.context_processor
    def inject_owner_stats():
        """
        Sidebar badge counts for theater owner pages.
        Always returns a fully-keyed dict so templates can safely access any key.
        """
        _empty = {"theaters": 0, "screens": 0, "shows": 0, "total_bookings": 0, "pending_bookings": 0}
        try:
            if current_user.is_authenticated and current_user.role == "theater_owner":
                from models.theater_model import Theater
                from models.screen_model  import Screen
                from models.booking_model import Booking
                from models.show_model    import Show
                from sqlalchemy import or_

                # Union logic: brand_id match OR direct owner_id assignment
                brand_id = getattr(current_user, "brand_id", None)
                uid      = current_user.user_id
                if brand_id:
                    theaters = Theater.query.filter(
                        or_(
                            Theater.brand_id == brand_id,
                            Theater.owner_id == uid,
                        )
                    ).all()
                else:
                    theaters = Theater.query.filter_by(owner_id=uid).all()

                theater_ids = [t.theater_id for t in theaters]
                screens_count  = Screen.query.filter(Screen.theater_id.in_(theater_ids)).count()  if theater_ids else 0
                shows_count    = Show.query.filter(Show.theater_id.in_(theater_ids)).count()       if theater_ids else 0
                bookings_count = (Booking.query.join(Booking.show)
                                  .filter(Show.theater_id.in_(theater_ids)).count())               if theater_ids else 0
                pending_count  = (Booking.query.join(Booking.show)
                                  .filter(Show.theater_id.in_(theater_ids),
                                          Booking.payment_status == "Pending").count())            if theater_ids else 0
                return {"owner_stats": {
                    "theaters":        len(theaters),
                    "screens":         screens_count,
                    "shows":           shows_count,
                    "total_bookings":  bookings_count,
                    "pending_bookings": pending_count,
                }}
        except Exception:
            pass
        return {"owner_stats": _empty}

    return app


def _seed_admin(User):
    if not User.query.filter_by(email="admin@gmail.com").first():
        admin = User(
            user_id = "US_ADMIN",
            name    = "Admin",
            email   = "admin@gmail.com",
            role    = "admin",
            city    = "Mumbai",
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("[SEED] Admin → admin@gmail.com / admin123")


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)

