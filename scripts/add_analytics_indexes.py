"""
add_analytics_indexes.py
========================
Run ONCE to speed up theater owner analytics queries.

    python scripts/add_analytics_indexes.py

Creates indexes on the hot join/filter columns used by owner_analytics.py.
Safe to run multiple times (uses IF NOT EXISTS).
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from database.db import db
from sqlalchemy import text

INDEXES = [
    # Bookings → Shows join (used in every analytics query)
    ("idx_bookings_show_id",
     "CREATE INDEX IF NOT EXISTS idx_bookings_show_id ON bookings(show_id)"),

    # Payments join + filter
    ("idx_payments_booking_id",
     "CREATE INDEX IF NOT EXISTS idx_payments_booking_id ON payments(booking_id)"),
    ("idx_payments_status",
     "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(transaction_status)"),
    ("idx_payments_booking_status",
     "CREATE INDEX IF NOT EXISTS idx_payments_booking_status ON payments(booking_id, transaction_status)"),

    # Shows → theater filter (scoped per owner)
    ("idx_shows_theater_id",
     "CREATE INDEX IF NOT EXISTS idx_shows_theater_id ON shows(theater_id)"),

    # Booking date range filters (monthly trend, daily pattern)
    ("idx_bookings_date",
     "CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date)"),

    # Seats → screen join (occupancy, seat type queries)
    ("idx_seats_screen_id",
     "CREATE INDEX IF NOT EXISTS idx_seats_screen_id ON seats(screen_id)"),
    ("idx_seats_status",
     "CREATE INDEX IF NOT EXISTS idx_seats_status ON seats(status)"),

    # Screens → theater filter
    ("idx_screens_theater_id",
     "CREATE INDEX IF NOT EXISTS idx_screens_theater_id ON screens(theater_id)"),

    # Shows → movie join
    ("idx_shows_movie_id_theater",
     "CREATE INDEX IF NOT EXISTS idx_shows_movie_id_theater ON shows(movie_id, theater_id)"),

    # Theater owner/brand lookup
    ("idx_theaters_owner_id",
     "CREATE INDEX IF NOT EXISTS idx_theaters_owner_id ON theaters(owner_id)"),
    ("idx_theaters_brand_id",
     "CREATE INDEX IF NOT EXISTS idx_theaters_brand_id ON theaters(brand_id)"),
]


def main():
    app = create_app()
    with app.app_context():
        print("\n🔧 Creating analytics indexes...\n")
        ok = 0
        for name, sql in INDEXES:
            print(f"   {name}...", end=" ", flush=True)
            try:
                db.session.execute(text(sql))
                db.session.commit()
                print("✅")
                ok += 1
            except Exception as e:
                db.session.rollback()
                print(f"⚠️  {e}")

        print(f"\n✅ Done! {ok}/{len(INDEXES)} indexes created.")
        print("🚀 Restart Flask — analytics should load significantly faster.\n")


if __name__ == "__main__":
    main()
