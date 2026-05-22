"""
seed_shows_final.py - Fixed to pick 2 different theaters
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, timedelta
from app import create_app
from database.db import db
from sqlalchemy import text

DAYS_AHEAD = 3
PRICE      = 149.99
SLOTS      = ["10:00", "20:30"]

def run():
    app = create_app()
    with app.app_context():

        print("\n🎬  CineHub — Final Show Seeder")
        print("=" * 45)

        conn = db.session

        # Pick 2 DIFFERENT theaters (one screen each)
        theaters = conn.execute(text("""
            SELECT DISTINCT ON (t.theater_id)
                   t.theater_id, t.name, t.city, s.screen_id, s.total_seats
            FROM   theaters t
            JOIN   screens  s ON s.theater_id = t.theater_id
            WHERE  t.status = 'Active'
            ORDER  BY t.theater_id, s.screen_id
            LIMIT  2
        """)).fetchall()

        if not theaters:
            print("\n❌  No theaters with screens found.\n")
            return

        print(f"\n🏢  Using theaters:")
        for t_id, name, city, s_id, seats in theaters:
            print(f"     [{t_id}] {name} ({city})  screen={s_id}  seats={seats}")

        # Delete existing shows
        old = conn.execute(text("SELECT COUNT(*) FROM shows")).scalar()
        if old > 0:
            print(f"\n🗑️   Deleting {old:,} old shows...")
            conn.execute(text("DELETE FROM shows"))
            conn.commit()
            print("    ✅  Cleared.")

        # Load all movies
        movie_ids = [r[0] for r in conn.execute(
            text("SELECT movie_id FROM movies ORDER BY movie_id")
        ).fetchall()]

        total_est = len(movie_ids) * len(theaters) * DAYS_AHEAD * len(SLOTS)
        print(f"\n📊  {len(movie_ids):,} movies × {len(theaters)} theaters"
              f" × {DAYS_AHEAD} days × {len(SLOTS)} slots = {total_est:,} shows")
        print(f"\n🚀  Inserting shows...\n")

        today   = date.today()
        counter = 0
        buf     = []
        done    = 0

        def flush(b):
            if not b: return 0
            db.session.execute(text(
                "INSERT INTO shows(show_id,movie_id,theater_id,screen_id,"
                "show_date,start_time,price_per_ticket,available_seats)"
                f"VALUES {','.join(b)} ON CONFLICT(show_id) DO NOTHING"
            ))
            db.session.commit()
            return len(b)

        for mid in movie_ids:
            for t_id, name, city, s_id, seats in theaters:
                for day in range(DAYS_AHEAD):
                    d = str(today + timedelta(days=day))
                    for slot in SLOTS:
                        counter += 1
                        buf.append(
                            f"('SH_{counter}','{mid}','{t_id}',"
                            f"'{s_id}','{d}','{slot}',{PRICE},{seats or 150})"
                        )
                        if len(buf) >= 500:
                            done += flush(buf)
                            buf   = []
                            print(f"   ✅  {done:,} / {total_est:,} shows...", end="\r")

        done += flush(buf)
        print(f"   ✅  {done:,} shows inserted.          ")

        fs = conn.execute(text("SELECT COUNT(*) FROM shows")).scalar()
        print(f"\n{'=' * 45}")
        print(f"✅  ALL DONE!")
        print(f"   Movies  : {len(movie_ids):,}")
        print(f"   Shows   : {fs:,}")
        print(f"   Range   : {today} → {today + timedelta(days=DAYS_AHEAD-1)}")
        print(f"\n💡  Run refresh_shows.py daily to keep dates rolling forever.\n")

if __name__ == "__main__":
    run()
