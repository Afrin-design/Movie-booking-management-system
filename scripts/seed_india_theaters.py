"""
seed_india_theaters.py
======================
Seeds theaters, screens, and shows for all major Indian cities.

Run from your project root:
    python scripts/seed_india_theaters.py

Features:
  • Assigns 2-4 theaters per city (not all theaters in every city)
  • Creates 2-3 screens per theater
  • Generates 7 days of upcoming shows for every screen
  • Idempotent — safe to re-run (skips duplicates)
"""

import sys, os, random
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, timedelta
from app import create_app
from database.db import db
from sqlalchemy import text

# ── CONFIG ────────────────────────────────────────────────────────────────────
DAYS_AHEAD  = 7
PRICE       = 149.99

SLOTS = [
    ("Morning",    "10:00"),
    ("Matinee",    "13:00"),
    ("Evening",    "16:30"),
    ("Night",      "19:30"),
    ("Late Night", "22:00"),
]

# Indian cities with state info
INDIA_CITIES = [
    # Metro / Tier-1
    ("Mumbai",       "Maharashtra"),
    ("Delhi",        "Delhi"),
    ("Bangalore",    "Karnataka"),
    ("Hyderabad",    "Telangana"),
    ("Chennai",      "Tamil Nadu"),
    ("Kolkata",      "West Bengal"),
    ("Pune",         "Maharashtra"),
    ("Ahmedabad",    "Gujarat"),
    ("Jaipur",       "Rajasthan"),
    ("Kochi",        "Kerala"),
    # Tier-2
    ("Lucknow",      "Uttar Pradesh"),
    ("Surat",        "Gujarat"),
    ("Nagpur",       "Maharashtra"),
    ("Indore",       "Madhya Pradesh"),
    ("Bhopal",       "Madhya Pradesh"),
    ("Visakhapatnam","Andhra Pradesh"),
    ("Patna",        "Bihar"),
    ("Vadodara",     "Gujarat"),
    ("Coimbatore",   "Tamil Nadu"),
    ("Agra",         "Uttar Pradesh"),
    ("Varanasi",     "Uttar Pradesh"),
    ("Chandigarh",   "Punjab"),
    ("Rajkot",       "Gujarat"),
    ("Ludhiana",     "Punjab"),
    ("Kanpur",       "Uttar Pradesh"),
    ("Nashik",       "Maharashtra"),
    ("Mysore",       "Karnataka"),
    ("Ranchi",       "Jharkhand"),
    ("Guwahati",     "Assam"),
    ("Thiruvananthapuram", "Kerala"),
    ("Madurai",      "Tamil Nadu"),
    ("Vijayawada",   "Andhra Pradesh"),
    ("Amritsar",     "Punjab"),
    ("Jodhpur",      "Rajasthan"),
    ("Raipur",       "Chhattisgarh"),
    ("Dehradun",     "Uttarakhand"),
    ("Bhubaneswar",  "Odisha"),
    ("Mangalore",    "Karnataka"),
    ("Hubli",        "Karnataka"),
    ("Kurnool",      "Andhra Pradesh"),
]

# Theater brands per city – distributed, not repeated in every city
THEATER_BRANDS = [
    "PVR Cinemas",
    "INOX Cinemas",
    "Cinepolis",
    "Carnival Cinemas",
    "SPI Cinemas",
    "MovieMax",
    "Miraj Cinemas",
    "G7 Multiplex",
    "Usha Multiplex",
    "Sathyam Cinemas",
]

# Neighborhood / locality patterns by state (fallback used generically)
LOCALITIES = [
    "Central Mall", "City Square", "Grand Plaza", "Metro Hub", "Phoenix Mall",
    "Orion Centre", "Forum Nexus", "VR Mall", "Lulu Hypermarket", "Mantri Square",
    "Prestige Forum", "Nexus Shantiniketan", "Elante Mall", "Pacific Mall",
    "Ambience Mall", "Select City Walk", "DLF Mall", "Infiniti Mall", "R-City Mall",
    "Growel's 101", "Nirmal Lifestyle", "Seawoods Grand", "Logix City Centre",
]


def _get_or_create_tables():
    """Ensure all tables exist."""
    db.create_all()


def _max_id(table, id_col, prefix):
    """Get the current max numeric id for a given table/column/prefix."""
    row = db.session.execute(text(f"""
        SELECT COALESCE(MAX(
            CAST(REGEXP_REPLACE({id_col}, '[^0-9]', '', 'g') AS INTEGER)
        ), 0)
        FROM {table}
        WHERE {id_col} ~ '[0-9]'
    """)).scalar()
    return int(row or 0)


def seed_theaters_and_screens():
    """Create theaters and screens for each city. Returns dict: theater_id → screen_id."""
    print("\n🏢  Seeding theaters and screens…")

    existing_cities = {
        row[0] for row in db.session.execute(
            text("SELECT DISTINCT city FROM theaters WHERE city IS NOT NULL")
        ).fetchall()
    }

    max_th = _max_id("theaters", "theater_id", "TH_")
    max_sc = _max_id("screens",  "screen_id",  "SC_")

    # theater_id → (screen_id, capacity)
    theater_screen_map = {}

    # Collect existing theater→screen mapping
    existing_rows = db.session.execute(text("""
        SELECT t.theater_id, s.screen_id, s.total_seats
        FROM theaters t
        JOIN screens s ON s.theater_id = t.theater_id
        ORDER BY s.screen_id
    """)).fetchall()
    for tid, sid, seats in existing_rows:
        if tid not in theater_screen_map:
            theater_screen_map[tid] = (sid, seats or 100)

    random.seed(42)
    brands_cycle = THEATER_BRANDS[:]

    for city, state in INDIA_CITIES:
        # How many theaters for this city: metros get 3-4, others 2-3
        is_metro = city in {"Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad"}
        count = random.randint(3, 4) if is_metro else random.randint(2, 3)

        # Check how many theaters already exist for this city
        existing_count = db.session.execute(text(
            "SELECT COUNT(*) FROM theaters WHERE city = :c"
        ), {"c": city}).scalar() or 0

        needed = max(0, count - existing_count)
        if needed == 0:
            print(f"   ✅  {city:22s}  (already has {existing_count} theater(s))")
            continue

        for i in range(needed):
            brand = brands_cycle[(max_th + i) % len(brands_cycle)]
            locality = random.choice(LOCALITIES)
            theater_name = f"{brand} – {city}"
            if needed > 1:
                theater_name = f"{brand} {city} {chr(65 + existing_count + i)}"

            max_th += 1
            tid = f"TH_{max_th}"

            db.session.execute(text("""
                INSERT INTO theaters (theater_id, name, location, city, state, status)
                VALUES (:tid, :name, :loc, :city, :state, 'Active')
                ON CONFLICT (theater_id) DO NOTHING
            """), {
                "tid":   tid,
                "name":  theater_name,
                "loc":   f"{locality}, {city}",
                "city":  city,
                "state": state,
            })

            # Create 2-3 screens for this theater
            num_screens = random.randint(2, 3)
            for sc_num in range(1, num_screens + 1):
                max_sc += 1
                sid = f"SC_{max_sc}"
                gold_s    = random.choice([20, 30, 40])
                silver_s  = random.choice([40, 50, 60])
                general_s = random.choice([60, 80, 100])
                total     = gold_s + silver_s + general_s

                db.session.execute(text("""
                    INSERT INTO screens
                        (screen_id, theater_id, screen_number,
                         total_seats, gold_seats, silver_seats, general_seats)
                    VALUES (:sid, :tid, :snum, :tot, :gold, :silver, :gen)
                    ON CONFLICT (screen_id) DO NOTHING
                """), {
                    "sid":    sid,
                    "tid":    tid,
                    "snum":   sc_num,
                    "tot":    total,
                    "gold":   gold_s,
                    "silver": silver_s,
                    "gen":    general_s,
                })

                if tid not in theater_screen_map:
                    theater_screen_map[tid] = (sid, total)

        db.session.commit()
        total_now = existing_count + needed
        print(f"   ➕  {city:22s}  +{needed} theater(s) → {total_now} total")

    print(f"\n   📊  Total theater-screen pairs ready: {len(theater_screen_map)}")
    return theater_screen_map


def seed_shows(theater_screen_map):
    """Generate upcoming shows for every theater/screen that has none."""
    print("\n🎬  Seeding shows…")

    movies = db.session.execute(text(
        "SELECT movie_id FROM movies ORDER BY movie_id"
    )).fetchall()
    movie_ids = [r[0] for r in movies]

    if not movie_ids:
        print("   ❌  No movies found – add movies first!")
        return

    max_sh = _max_id("shows", "show_id", "SH_")
    today  = date.today()
    slot_times = [t for _, t in SLOTS]

    total_created = 0
    total_skipped = 0

    theater_list = list(theater_screen_map.items())

    for tid, (sid, cap) in theater_list:
        # Check if this theater already has future shows
        existing = db.session.execute(text("""
            SELECT COUNT(*) FROM shows
            WHERE theater_id = :tid AND show_date >= :today
        """), {"tid": tid, "today": str(today)}).scalar() or 0

        if existing > 0:
            print(f"   ⏭   Theater {tid:8s}: already has {existing} upcoming show(s)")
            total_skipped += existing
            continue

        rows = []
        # Distribute movies across theaters — each theater gets a subset
        # Use theater index to rotate which movies go here
        t_idx = theater_list.index((tid, (sid, cap)))
        stride = max(1, len(movie_ids) // len(theater_list))
        start_m = (t_idx * stride) % len(movie_ids)
        # Take min(8, total) movies for this theater
        subset_size = min(8, len(movie_ids))
        movie_subset = [movie_ids[(start_m + j) % len(movie_ids)] for j in range(subset_size)]

        for movie_id in movie_subset:
            for day_offset in range(DAYS_AHEAD):
                cur_date = str(today + timedelta(days=day_offset))
                for time_str in slot_times:
                    max_sh += 1
                    rows.append(
                        f"('SH_{max_sh}','{movie_id}','{tid}',"
                        f"'{sid}','{cur_date}','{time_str}',{PRICE},{cap})"
                    )

        if not rows:
            continue

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
            created = result.rowcount if result.rowcount >= 0 else len(rows)
            total_created += created
            city_row = db.session.execute(text(
                "SELECT city FROM theaters WHERE theater_id = :t"
            ), {"t": tid}).scalar() or "?"
            print(f"   ✅  Theater {tid:8s} ({city_row:20s}): +{created} shows")
        except Exception as e:
            db.session.rollback()
            print(f"   ❌  Theater {tid}: ERROR – {e}")

    print(f"\n   📊  Shows created: {total_created:,}  |  Already existed: {total_skipped:,}")


def create_indexes():
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
        ("idx_theaters_city",
         "CREATE INDEX IF NOT EXISTS idx_theaters_city "
         "ON theaters(city)"),
    ]
    print("\n🔧  Creating performance indexes…")
    for name, sql in indexes:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            print(f"   ✅  {name}")
        except Exception as e:
            db.session.rollback()
            print(f"   ⚠️  {name} – {e}")


def run():
    app = create_app()
    with app.app_context():
        print("\n🇮🇳  CineHub – India Theater & Show Seeder")
        print("=" * 50)

        _get_or_create_tables()
        theater_screen_map = seed_theaters_and_screens()
        seed_shows(theater_screen_map)
        create_indexes()

        # Summary
        city_count = db.session.execute(
            text("SELECT COUNT(DISTINCT city) FROM theaters WHERE city IS NOT NULL")
        ).scalar()
        th_count = db.session.execute(text("SELECT COUNT(*) FROM theaters")).scalar()
        sh_count = db.session.execute(
            text("SELECT COUNT(*) FROM shows WHERE show_date >= CURRENT_DATE")
        ).scalar()

        print(f"\n{'=' * 50}")
        print(f"✅  ALL DONE!")
        print(f"   Cities with theaters : {city_count}")
        print(f"   Total theaters       : {th_count}")
        print(f"   Upcoming shows       : {sh_count:,}")
        print(f"\n🚀  Every city now has theaters and available shows!\n")


if __name__ == "__main__":
    run()
