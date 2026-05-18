"""
generate_upcoming_shows.py
==========================
Run from your project root:

    python scripts/generate_upcoming_shows.py

Processes ALL movies in chunks of 20 — safe, fast, no freeze.
Each chunk inserts ~700 rows in ~0.5 s.
Automatically creates DB indexes at the end for fast page loads.

Progress bar example:
   [████░░░░░░░░░░░░░░░░]  20.0%  chunk 10  |  movies 1-200   |  +1000 shows
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── CONFIG ────────────────────────────────────────────────────────────────────
MAX_THEATERS = 10
DAYS_AHEAD   = 7
PRICE        = 149.99
CHUNK_SIZE   = 20

SLOTS = [
    ("Morning",    "10:00"),
    ("Matinee",    "13:00"),
    ("Evening",    "16:30"),
    ("Night",      "19:30"),
    ("Late Night", "22:00"),
]
# ─────────────────────────────────────────────────────────────────────────────

from datetime import date, timedelta
from app import create_app
from database.db import db
from sqlalchemy import text


def create_indexes():
    """Create performance indexes on shows table (safe to re-run)."""
    indexes = [
        ("idx_shows_movie_date_avail",
         "CREATE INDEX IF NOT EXISTS idx_shows_movie_date_avail "
         "ON shows(movie_id, show_date, available_seats)"),
        ("idx_shows_theater_date",
         "CREATE INDEX IF NOT EXISTS idx_shows_theater_date "
         "ON shows(theater_id, show_date)"),
        ("idx_shows_date_avail",
         "CREATE INDEX IF NOT EXISTS idx_shows_date_avail "
         "ON shows(show_date, available_seats)"),
        ("idx_shows_movie_id",
         "CREATE INDEX IF NOT EXISTS idx_shows_movie_id "
         "ON shows(movie_id)"),
    ]
    print("\n🔧  Creating performance indexes on shows table...")
    for name, sql in indexes:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            print(f"   ✅  {name}")
        except Exception as e:
            db.session.rollback()
            print(f"   ⚠️  {name} -- {e}")
    print("   Done.\n")


def run():
    app = create_app()
    with app.app_context():

        print("\n🎬  CineHub -- Upcoming Show Generator (ALL MOVIES)")
        print("=" * 54)

        total_movies = db.session.execute(
            text("SELECT COUNT(*) FROM movies")
        ).scalar()

        print(f"   Total movies  : {total_movies:,}")
        print(f"   Chunk size    : {CHUNK_SIZE} movies per batch")
        print(f"   Theaters used : {MAX_THEATERS}")
        print(f"   Days ahead    : {DAYS_AHEAD}")
        print(f"   Slots/day     : {len(SLOTS)}")
        total_est = total_movies * MAX_THEATERS * DAYS_AHEAD * len(SLOTS)
        print(f"   Total est.    : {total_est:,} shows")
        print("=" * 54)

        screens = db.session.execute(text(f"""
            SELECT s.theater_id, s.screen_id, s.total_seats, t.name, t.city
            FROM   screens s
            JOIN   theaters t ON t.theater_id = s.theater_id
            WHERE  t.status = 'Active'
            ORDER  BY s.screen_id
            LIMIT  {MAX_THEATERS * 3}
        """)).fetchall()

        screen_by_theater = {}
        for t_id, s_id, seats, t_name, city in screens:
            if t_id not in screen_by_theater:
                screen_by_theater[t_id] = (s_id, seats or 100, t_name, city)
            if len(screen_by_theater) >= MAX_THEATERS:
                break

        if not screen_by_theater:
            print("\n❌  No active theaters with screens found.\n")
            return

        print(f"\n✅  Using {len(screen_by_theater)} theater(s):")
        for t_id, (s_id, cap, t_name, city) in screen_by_theater.items():
            print(f"     • {t_name} ({city})")

        row = db.session.execute(text("""
            SELECT COALESCE(MAX(
                CAST(REGEXP_REPLACE(show_id, '[^0-9]', '', 'g') AS INTEGER)
            ), 0)
            FROM shows WHERE show_id ~ '[0-9]'
        """)).scalar()
        max_n = int(row or 0)
        print(f"\n✅  Starting from show number : SH_{max_n + 1}")

        today         = date.today()
        slot_times    = [t for _, t in SLOTS]
        total_created = 0
        total_skipped = 0
        offset        = 0
        chunk_num     = 0

        print(f"\n🚀  Processing all {total_movies:,} movies in chunks of {CHUNK_SIZE}...\n")

        while True:
            movies = db.session.execute(text(f"""
                SELECT movie_id, title FROM movies
                ORDER BY movie_id
                LIMIT {CHUNK_SIZE} OFFSET {offset}
            """)).fetchall()

            if not movies:
                break

            chunk_num += 1
            rows = []

            for movie_id, title in movies:
                for theater_id, (screen_id, cap, t_name, city) in screen_by_theater.items():
                    for day_offset in range(DAYS_AHEAD):
                        cur_date = str(today + timedelta(days=day_offset))
                        for time_str in slot_times:
                            max_n += 1
                            rows.append(
                                f"('SH_{max_n}','{movie_id}','{theater_id}',"
                                f"'{screen_id}','{cur_date}','{time_str}',{PRICE},{cap})"
                            )

            sql = text(f"""
                INSERT INTO shows
                    (show_id, movie_id, theater_id, screen_id,
                     show_date, start_time, price_per_ticket, available_seats)
                VALUES {','.join(rows)}
                ON CONFLICT DO NOTHING
            """)

            try:
                result = db.session.execute(sql)
                db.session.commit()
                created  = result.rowcount if result.rowcount >= 0 else len(rows)
                skipped  = len(rows) - created
                total_created += created
                total_skipped += skipped

                done_movies = min(offset + CHUNK_SIZE, total_movies)
                pct         = (done_movies / total_movies) * 100
                bar_filled  = int(pct / 5)
                bar         = "=>" * bar_filled + ".." * (20 - bar_filled)
                print(
                    f"   [{bar}] {pct:5.1f}%"
                    f"  chunk {chunk_num}"
                    f"  |  movies {offset+1}-{done_movies}"
                    f"  |  +{created} shows"
                )

            except Exception as e:
                db.session.rollback()
                print(f"\n❌  Error at chunk {chunk_num} (offset {offset}): {e}")
                print("    Skipping this chunk and continuing...\n")

            offset += CHUNK_SIZE

        print(f"\n{'=' * 54}")
        print(f"✅  ALL DONE!")
        print(f"   Total created : {total_created:,} new show(s)")
        print(f"   Total skipped : {total_skipped:,} duplicate(s)")
        print(f"   Movies covered: {total_movies:,}")
        print(f"   Theaters used : {len(screen_by_theater)}")
        print(f"\n🎟️  Every movie now has shows for the next {DAYS_AHEAD} days.")

        create_indexes()

        print("🚀  Your app is ready -- open the home page!\n")


if __name__ == "__main__":
    run()
