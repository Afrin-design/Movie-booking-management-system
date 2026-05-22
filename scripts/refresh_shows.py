"""
refresh_shows.py
================
Run from your project root:

    python scripts/refresh_shows.py

Rolls expired show dates FORWARD without creating duplicates.
Much lighter than reset_and_seed_shows.py — use this daily.

Schedule example (cron, runs every morning at 6am):
    0 6 * * * cd /your/project && python scripts/refresh_shows.py

Logic:
  - Finds shows where show_date < today
  - Reassigns each to a future date (cycling across next 7 days)
  - Resets available_seats to screen capacity
  - No new rows created — just dates updated
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, timedelta
from app import create_app
from database.db import db
from sqlalchemy import text

DAYS_AHEAD = 7   # Roll expired shows into next N days

def run():
    app = create_app()
    with app.app_context():

        print("\n🎬  CineHub — Show Date Refresher")
        print("=" * 45)

        today    = date.today()
        end_date = today + timedelta(days=DAYS_AHEAD - 1)

        expired = db.session.execute(
            text("SELECT COUNT(*) FROM shows WHERE show_date < :today"),
            {"today": today}
        ).scalar()

        print(f"   Today         : {today}")
        print(f"   Expired shows : {expired:,}")
        print("=" * 45)

        if expired == 0:
            print("\n✅  No expired shows — all dates are current!\n")
            return

        print(f"\n🚀  Rolling {expired:,} expired shows forward...\n")

        # Spread expired shows evenly across the next DAYS_AHEAD days
        # Uses a deterministic offset based on show_id number so every
        # slot gets an even spread (not all landing on the same day).
        db.session.execute(text("""
            UPDATE shows
            SET
                show_date = :today + (
                    MOD(
                        ABS(CAST(REGEXP_REPLACE(show_id, '[^0-9]', '', 'g') AS INTEGER)),
                        :days_ahead
                    )
                ) * INTERVAL '1 day',
                available_seats = COALESCE(
                    (SELECT s.total_seats
                     FROM   screens s
                     WHERE  s.screen_id = shows.screen_id),
                    available_seats
                )
            WHERE show_date < :today
        """), {"today": today, "days_ahead": DAYS_AHEAD})

        db.session.commit()

        updated = db.session.execute(
            text("SELECT COUNT(*) FROM shows WHERE show_date BETWEEN :today AND :end"),
            {"today": today, "end": end_date}
        ).scalar()

        print(f"✅  Done!")
        print(f"   Shows refreshed : {expired:,}")
        print(f"   Active range    : {today} → {end_date}")
        print(f"   Shows in range  : {updated:,}")
        print(f"\n🎟️  All shows are live for the next {DAYS_AHEAD} days!\n")


if __name__ == "__main__":
    run()
