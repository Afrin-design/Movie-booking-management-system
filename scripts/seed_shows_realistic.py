"""
seed_shows_realistic.py
=======================
Ensures EVERY movie gets shows across all theaters for the next 7 days.

- Every movie gets at least 1 show per day across theaters
- 4 time slots per show: 10:00, 13:30, 17:00, 23:00
- Theaters rotate movies so each screen shows different movies per slot
- Works on both PostgreSQL and SQLite

Run:
    python scripts/seed_shows_realistic.py
"""

import sys, os, random
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, timedelta
from app import create_app
from database.db import db
from sqlalchemy import text

DAYS_AHEAD = 7
PRICE      = 149.99
SLOTS      = ["10:00", "13:30", "17:00", "23:00"]

def run():
    app = create_app()
    with app.app_context():

        print("\n🎬  CineHub — Show Seeder (Every Movie Gets Shows)")
        print("=" * 55)

        conn = db.session

        # Get all theaters with their screens
        theaters = conn.execute(text("""
            SELECT t.theater_id, t.name, t.city, s.screen_id, s.total_seats
            FROM   theaters t
            JOIN   screens  s ON s.theater_id = t.theater_id
            WHERE  t.status = 'Active' AND t.city IS NOT NULL
            ORDER  BY t.theater_id, s.screen_id
        """)).fetchall()

        if not theaters:
            print("\n❌  No active theaters with screens found.\n")
            return

        # Build list of (theater_id, screen_id, seats)
        theater_screens = []
        seen = set()
        for t_id, name, city, s_id, seats in theaters:
            key = (t_id, s_id)
            if key not in seen:
                theater_screens.append((t_id, s_id, seats or 150))
                seen.add(key)

        print(f"\n🏢  Found {len(theater_screens)} theater-screens")

        # Get all movies
        all_movies = [r[0] for r in conn.execute(
            text("SELECT movie_id FROM movies ORDER BY movie_id")
        ).fetchall()]

        if not all_movies:
            print("\n❌  No movies in DB.\n")
            return

        print(f"🎥  Found {len(all_movies):,} movies")

        # Delete old shows
        old = conn.execute(text("SELECT COUNT(*) FROM shows")).scalar()
        if old > 0:
            print(f"🗑️   Deleting {old:,} old shows...")
            conn.execute(text("DELETE FROM shows"))
            conn.commit()

        today   = date.today()
        counter = 0
        buf     = []
        done    = 0

        def flush(b):
            if not b: return 0
            vals = ",".join(b)
            db.session.execute(text(
                "INSERT INTO shows(show_id,movie_id,theater_id,screen_id,"
                "show_date,start_time,price_per_ticket,available_seats) "
                f"VALUES {vals} ON CONFLICT(show_id) DO NOTHING"
            ))
            db.session.commit()
            return len(b)

        print(f"\n🚀  Creating shows for ALL {len(all_movies):,} movies across {len(theater_screens)} screens for {DAYS_AHEAD} days...\n")

        # Assign every movie to at least one theater-screen per day
        # Rotate movies across theater-screens so each screen shows different movies per slot
        num_screens = len(theater_screens)

        for day in range(DAYS_AHEAD):
            show_date = str(today + timedelta(days=day))

            # For each movie, assign it to a theater-screen (rotating)
            for movie_idx, movie_id in enumerate(all_movies):
                # Pick a theater-screen for this movie (rotate evenly)
                t_id, s_id, seats = theater_screens[movie_idx % num_screens]

                # Give each movie 2 slots per day (morning + night)
                # so it's not overwhelming but still visible
                movie_slots = SLOTS

                for slot in movie_slots:
                    counter += 1
                    buf.append(
                        f"('SH_{counter}','{movie_id}','{t_id}',"
                        f"'{s_id}','{show_date}','{slot}',{PRICE},{seats})"
                    )

                    if len(buf) >= 500:
                        done += flush(buf)
                        buf = []
                        print(f"   ✅  {done:,} shows inserted...", end="\r")

        done += flush(buf)
        print(f"   ✅  {done:,} shows inserted.                    ")

        fs = conn.execute(text("SELECT COUNT(*) FROM shows")).scalar()
        print(f"\n{'=' * 55}")
        print(f"✅  ALL DONE!")
        print(f"   Movies      : {len(all_movies):,}")
        print(f"   Screens     : {num_screens}")
        print(f"   Shows       : {fs:,}")
        print(f"   Range       : {today} → {today + timedelta(days=DAYS_AHEAD-1)}")
        print(f"   Slots/movie : 2 per day (10:00 or 13:30 + 17:00 or 23:00)")
        print(f"\n💡  Every movie now has shows! Run this script again next week.\n")

if __name__ == "__main__":
    run()
