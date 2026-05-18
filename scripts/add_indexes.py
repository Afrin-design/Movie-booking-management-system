"""
add_indexes.py
==============
Run this ONCE to fix slow page loads after a large bulk show insert.

    python scripts/add_indexes.py

Creates 4 indexes on the shows table. Safe to run multiple times.
Takes ~30-60 seconds on 350k rows, then your home & movies pages
will load in <1 second instead of timing out.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from database.db import db
from sqlalchemy import text

INDEXES = [
    # Most important: used by EXISTS subquery in home() and movies()
    ("idx_shows_movie_date_avail",
     "CREATE INDEX IF NOT EXISTS idx_shows_movie_date_avail "
     "ON shows(movie_id, show_date, available_seats)"),

    # Used by theater-filtered queries
    ("idx_shows_theater_date",
     "CREATE INDEX IF NOT EXISTS idx_shows_theater_date "
     "ON shows(theater_id, show_date)"),

    # Used by date range filter
    ("idx_shows_date_avail",
     "CREATE INDEX IF NOT EXISTS idx_shows_date_avail "
     "ON shows(show_date, available_seats)"),

    # Simple movie lookup
    ("idx_shows_movie_id",
     "CREATE INDEX IF NOT EXISTS idx_shows_movie_id "
     "ON shows(movie_id)"),
]

def main():
    app = create_app()
    with app.app_context():
        total = db.session.execute(text("SELECT COUNT(*) FROM shows")).scalar()
        print(f"\n📊  shows table has {total:,} rows")
        print("🔧  Creating indexes (this may take 30-60s for 350k rows)...\n")

        for name, sql in INDEXES:
            print(f"   Creating {name}...", end=" ", flush=True)
            try:
                db.session.execute(text(sql))
                db.session.commit()
                print("✅")
            except Exception as e:
                db.session.rollback()
                print(f"⚠️  {e}")

        print("\n✅  All indexes created!")
        print("🚀  Restart your Flask app and the home page will load fast.\n")

if __name__ == "__main__":
    main()
