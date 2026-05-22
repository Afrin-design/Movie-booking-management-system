"""
seed_india_theaters.py
======================
Run from your project root:

    python scripts/seed_india_theaters.py

Creates exactly 2 theaters per city for all major Indian cities.
Each theater gets 1 screen. Safe to re-run — skips cities that
already have 2 theaters.

Run this ONCE. Then run reset_and_seed_shows.py for shows.
"""

import sys, os, random
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from database.db import db
from sqlalchemy import text

THEATERS_PER_CITY = 2

# All major Indian cities
INDIA_CITIES = [
    ("Mumbai",              "Maharashtra"),
    ("Delhi",               "Delhi"),
    ("Bangalore",           "Karnataka"),
    ("Hyderabad",           "Telangana"),
    ("Chennai",             "Tamil Nadu"),
    ("Kolkata",             "West Bengal"),
    ("Pune",                "Maharashtra"),
    ("Ahmedabad",           "Gujarat"),
    ("Jaipur",              "Rajasthan"),
    ("Kochi",               "Kerala"),
    ("Lucknow",             "Uttar Pradesh"),
    ("Surat",               "Gujarat"),
    ("Nagpur",              "Maharashtra"),
    ("Indore",              "Madhya Pradesh"),
    ("Bhopal",              "Madhya Pradesh"),
    ("Visakhapatnam",       "Andhra Pradesh"),
    ("Patna",               "Bihar"),
    ("Vadodara",            "Gujarat"),
    ("Coimbatore",          "Tamil Nadu"),
    ("Agra",                "Uttar Pradesh"),
    ("Varanasi",            "Uttar Pradesh"),
    ("Chandigarh",          "Punjab"),
    ("Rajkot",              "Gujarat"),
    ("Ludhiana",            "Punjab"),
    ("Kanpur",              "Uttar Pradesh"),
    ("Nashik",              "Maharashtra"),
    ("Mysore",              "Karnataka"),
    ("Ranchi",              "Jharkhand"),
    ("Guwahati",            "Assam"),
    ("Thiruvananthapuram",  "Kerala"),
    ("Madurai",             "Tamil Nadu"),
    ("Vijayawada",          "Andhra Pradesh"),
    ("Amritsar",            "Punjab"),
    ("Jodhpur",             "Rajasthan"),
    ("Raipur",              "Chhattisgarh"),
    ("Dehradun",            "Uttarakhand"),
    ("Bhubaneswar",         "Odisha"),
    ("Mangalore",           "Karnataka"),
    ("Hubli",               "Karnataka"),
    ("Kurnool",             "Andhra Pradesh"),
]

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

LOCALITIES = [
    "Central Mall", "City Square", "Grand Plaza", "Metro Hub", "Phoenix Mall",
    "Orion Centre", "Forum Nexus", "VR Mall", "Lulu Hypermarket", "Mantri Square",
    "Prestige Forum", "Nexus Shantiniketan", "Elante Mall", "Pacific Mall",
    "Ambience Mall", "Select City Walk", "DLF Mall", "Infiniti Mall", "R-City Mall",
]


def _max_id(table, id_col):
    row = db.session.execute(text(f"""
        SELECT COALESCE(MAX(
            CAST(REGEXP_REPLACE({id_col}, '[^0-9]', '', 'g') AS INTEGER)
        ), 0)
        FROM {table}
        WHERE {id_col} ~ '[0-9]'
    """)).scalar()
    return int(row or 0)


def run():
    app = create_app()
    with app.app_context():
        print("\n🇮🇳  CineHub — India Theater Seeder")
        print("=" * 50)
        print(f"   Cities       : {len(INDIA_CITIES)}")
        print(f"   Per city     : {THEATERS_PER_CITY} theaters")
        print(f"   Total target : {len(INDIA_CITIES) * THEATERS_PER_CITY} theaters")
        print("=" * 50)

        random.seed(42)
        max_th = _max_id("theaters", "theater_id")
        max_sc = _max_id("screens",  "screen_id")

        created_theaters = 0
        created_screens  = 0

        for city, state in INDIA_CITIES:
            existing = db.session.execute(
                text("SELECT COUNT(*) FROM theaters WHERE city = :c"),
                {"c": city}
            ).scalar() or 0

            needed = max(0, THEATERS_PER_CITY - existing)

            if needed == 0:
                print(f"   ✅  {city:25s} already has {existing} theater(s)")
                continue

            for i in range(needed):
                brand    = THEATER_BRANDS[(max_th) % len(THEATER_BRANDS)]
                locality = random.choice(LOCALITIES)
                slot     = existing + i + 1  # A or B

                # Name: "PVR Cinemas Mumbai A" / "PVR Cinemas Mumbai B"
                theater_name = f"{brand} {city} {'AB'[i % 2]}"

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

                # 1 screen per theater (clean and simple)
                max_sc += 1
                sid        = f"SC_{max_sc}"
                gold_s     = 30
                silver_s   = 50
                general_s  = 80
                total      = gold_s + silver_s + general_s   # 160 seats

                db.session.execute(text("""
                    INSERT INTO screens
                        (screen_id, theater_id, screen_number,
                         total_seats, gold_seats, silver_seats, general_seats)
                    VALUES (:sid, :tid, 1, :tot, :gold, :silver, :gen)
                    ON CONFLICT (screen_id) DO NOTHING
                """), {
                    "sid": sid, "tid": tid,
                    "tot": total, "gold": gold_s,
                    "silver": silver_s, "gen": general_s,
                })

                created_theaters += 1
                created_screens  += 1

            db.session.commit()
            print(f"   ➕  {city:25s} +{needed} theater(s) created")

        # Final count
        total_th = db.session.execute(text("SELECT COUNT(*) FROM theaters")).scalar()
        total_sc = db.session.execute(text("SELECT COUNT(*) FROM screens")).scalar()
        cities   = db.session.execute(
            text("SELECT COUNT(DISTINCT city) FROM theaters WHERE city IS NOT NULL")
        ).scalar()

        print(f"\n{'=' * 50}")
        print(f"✅  ALL DONE!")
        print(f"   New theaters created  : {created_theaters}")
        print(f"   New screens created   : {created_screens}")
        print(f"   Cities with theaters  : {cities}")
        print(f"   Total theaters in DB  : {total_th}")
        print(f"   Total screens in DB   : {total_sc}")
        print(f"\n💡  Now run: python scripts/reset_and_seed_shows.py\n")


if __name__ == "__main__":
    run()
