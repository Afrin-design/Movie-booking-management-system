"""
reset_and_seed_shows.py
=======================
Run from your project root:

    python scripts/reset_and_seed_shows.py

What this script does:
  1. DELETES all existing shows
  2. Picks exactly 2 active theaters per city
  3. Creates shows: all movies × 2 theaters/city × 7 days × 4 slots
  4. Shows are always future-dated — never expire

Show count estimate:
    40 cities × 2 theaters × N movies × 7 days × 4 slots
    e.g. 50 movies  → ~112,000 shows
         100 movies → ~224,000 shows

To keep shows fresh, run daily via cron:
    0 6 * * * cd /your/project && python scripts/refresh_shows.py
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, timedelta
from app import create_app
from database.db import db
from sqlalchemy import text

# ── CONFIG ─────────────────────────────────────────────────────────────────────
THEATERS_PER_CITY = 2        # Exactly 2 theaters per city
DAYS_AHEAD        = 7        # Shows for next 7 days
PRICE             = 149.99   # Default ticket price

SLOTS = [
    ("Morning",  "10:00"),
    ("Matinee",  "13:30"),
    ("Evening",  "17:00"),
    ("Night",    "20:30"),
]
# ───────────────────────────────────────────────────────────────────────────────


def pick_theaters_per_city(conn):
    """Return up to THEATERS_PER_CITY active theaters per city, each with one screen."""
    rows = conn.execute(text("""
        SELECT t.city, t.theater_id, t.name,
               s.screen_id, s.total_seats
        FROM   theaters t
        JOIN   screens  s ON s.theater_id = t.theater_id
        WHERE  t.status = 'Active'
          AND  t.city IS NOT NULL
        ORDER  BY t.city, t.theater_id, s.screen_id
    """)).fetchall()

    # city → [(theater_id, name, screen_id, seats), ...]  — keep first 2 per city
    city_map = {}
    seen_theaters = set()
    for city, tid, tname, sid, seats in rows:
        if tid in seen_theaters:
            continue
        city_map.setdefault(city, [])
        if len(city_map[city]) < THEATERS_PER_CITY:
            city_map[city].append((tid, tname, sid, seats or 100))
            seen_theaters.add(tid)

    return city_map


def run():
    app = create_app()
    with app.app_context():

        print("\n🎬  CineHub — City-wise Show Seeder")
        print("=" * 55)

        conn = db.session

        # ── Step 1: Pick 2 theaters per city ──────────────────────────────────
        city_map = pick_theaters_per_city(conn)

        if not city_map:
            print("\n❌  No active theaters with screens found.")
            print("    Run seed_india_theaters.py first, then re-run this.\n")
            return

        total_theaters = sum(len(v) for v in city_map.values())
        print(f"\n✅  Cities found    : {len(city_map)}")
        print(f"✅  Theaters total  : {total_theaters}  ({THEATERS_PER_CITY} per city)\n")

        for city in sorted(city_map.keys()):
            theaters = city_map[city]
            for tid, tname, sid, cap in theaters:
                print(f"     {city:25s} → [{tid}] {tname}")

        # ── Step 2: Load all movies ────────────────────────────────────────────
        movies = conn.execute(
            text("SELECT movie_id, title FROM movies ORDER BY movie_id")
        ).fetchall()

        if not movies:
            print("\n❌  No movies in DB. Add movies first, then re-run.\n")
            return

        print(f"\n🎞️   Movies found   : {len(movies):,}")

        # ── Step 3: Delete all existing shows ─────────────────────────────────
        existing = conn.execute(text("SELECT COUNT(*) FROM shows")).scalar()
        print(f"🗑️   Deleting {existing:,} existing shows...")
        conn.execute(text("DELETE FROM shows"))
        conn.commit()
        print(f"    ✅  Deleted.")

        # ── Step 4: Generate shows ─────────────────────────────────────────────
        today       = date.today()
        slot_times  = [t for _, t in SLOTS]
        total_est   = len(movies) * total_theaters * DAYS_AHEAD * len(SLOTS)

        print(f"\n📅  Days ahead     : {DAYS_AHEAD}")
        print(f"⏰  Slots/day      : {len(SLOTS)}  {[s for s, _ in SLOTS]}")
        print(f"📊  Total shows    : ~{total_est:,}")
        print(f"\n🚀  Inserting in chunks of 500...\n")

        counter  = 0
        rows_buf = []
        inserted = 0

        def flush(buf):
            if not buf:
                return 0
            conn.execute(text(
                "INSERT INTO shows "
                "(show_id, movie_id, theater_id, screen_id, "
                " show_date, start_time, price_per_ticket, available_seats) "
                f"VALUES {', '.join(buf)} "
                "ON CONFLICT (show_id) DO NOTHING"
            ))
            conn.commit()
            return len(buf)

        for movie_id, title in movies:
            for city, theaters in city_map.items():
                for tid, tname, sid, cap in theaters:
                    for day_offset in range(DAYS_AHEAD):
                        show_date = str(today + timedelta(days=day_offset))
                        for time_str in slot_times:
                            counter += 1
                            rows_buf.append(
                                f"('SH_{counter}','{movie_id}','{tid}',"
                                f"'{sid}','{show_date}','{time_str}',{PRICE},{cap})"
                            )
                            if len(rows_buf) >= 500:
                                inserted += flush(rows_buf)
                                rows_buf = []
                                print(f"   ✅  {inserted:,} / {total_est:,} inserted...", end="\r")

        inserted += flush(rows_buf)
        print(f"   ✅  {inserted:,} / {total_est:,} inserted.          ")

        # ── Step 5: Summary ────────────────────────────────────────────────────
        final = conn.execute(text("SELECT COUNT(*) FROM shows")).scalar()
        print(f"\n{'=' * 55}")
        print(f"✅  ALL DONE!")
        print(f"   Shows in DB    : {final:,}")
        print(f"   Movies         : {len(movies):,}")
        print(f"   Cities         : {len(city_map)}")
        print(f"   Theaters       : {total_theaters}  ({THEATERS_PER_CITY}/city)")
        print(f"   Date range     : {today} → {today + timedelta(days=DAYS_AHEAD-1)}")
        print(f"\n💡  Run refresh_shows.py daily so dates never expire.\n")


if __name__ == "__main__":
    run()
