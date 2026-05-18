import sys
import os
import math
import pandas as pd
from datetime import datetime

# Allow running from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from database.db import db
from models.user_model    import User
from models.movie_model   import Movie
from models.theater_model import Theater
from models.screen_model  import Screen
from models.show_model    import Show
from models.booking_model import Booking
from models.payment_model import Payment
from models.seats_model   import Seat
from models.reviews_model import Review

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "..", "CineHub_Dataset.xlsx")
BATCH_SIZE = 1000 

def clean_id(val):
    """Force IDs to be clean strings, removing .0 from Excel floats."""
    if val is None or pd.isna(val):
        return None
    return str(val).split('.')[0].strip()

def clean(val):
    if val is None: return None
    try:
        if math.isnan(float(val)): return None
    except (TypeError, ValueError): pass
    return val

def to_date(val):
    val = clean(val)
    return val.date() if hasattr(val, "date") else val

def to_datetime(val):
    val = clean(val)
    if isinstance(val, datetime): return val
    if hasattr(val, "to_pydatetime"): return val.to_pydatetime()
    return val

def read_sheet(sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df.dropna(how="all", inplace=True)
    print(f"  [{sheet_name}] {len(df)} rows loaded")
    return df

def batch_upsert(session, objects: list, label: str):
    """Commits one-by-one to prevent one bad Foreign Key from stopping the script."""
    total = len(objects)
    inserted = 0
    skipped = 0
    print(f"  -> Processing {label}...")
    for obj in objects:
        try:
            session.merge(obj)
            session.commit()
            inserted += 1
        except Exception:
            session.rollback()
            skipped += 1
    print(f"  ✓ {label}: {inserted} successful, {skipped} skipped.\n")

# ── LOADERS ──────────────────────────────────────────────────────────────────

def load_users(session):
    df = read_sheet("Users")
    objects = [User(user_id=clean_id(row["user_id"]), name=clean(row.get("name")), email=clean(row.get("email")), phone_number=clean_id(row.get("phone_number"))) for _, row in df.iterrows()]
    batch_upsert(session, objects, "Users")

def load_movies(session):
    df = read_sheet("Movies")
    objects = [Movie(movie_id=clean_id(row["movie_id"]), title=clean(row.get("title")), genre=clean(row.get("genre")), rating=float(row["rating"]) if clean(row.get("rating")) else None) for _, row in df.iterrows()]
    batch_upsert(session, objects, "Movies")

def load_theaters(session):
    df = read_sheet("Theaters")
    objects = [Theater(theater_id=clean_id(row["theater_id"]), name=clean(row.get("name")), city=clean(row.get("city"))) for _, row in df.iterrows()]
    batch_upsert(session, objects, "Theaters")

def load_screens(session):
    df = read_sheet("Screens")
    objects = [Screen(screen_id=clean_id(row["screen_id"]), theater_id=clean_id(row["theater_id"]), screen_number=int(row["screen_number"]), total_seats=int(row["total_seats"])) for _, row in df.iterrows()]
    batch_upsert(session, objects, "Screens")

def load_shows(session):
    df = read_sheet("Shows")
    objects = [Show(show_id=clean_id(row["show_id"]), movie_id=clean_id(row["movie_id"]), theater_id=clean_id(row["theater_id"]), screen_id=clean_id(row["screen_id"]), price_per_ticket=float(row["price_per_ticket"])) for _, row in df.iterrows()]
    batch_upsert(session, objects, "Shows")

def load_bookings(session):
    df = read_sheet("Bookings")
    objects = [Booking(booking_id=clean_id(row["booking_id"]), user_id=clean_id(row["user_id"]), show_id=clean_id(row["show_id"]), payment_status=clean(row.get("payment_status")) or "Completed") for _, row in df.iterrows()]
    batch_upsert(session, objects, "Bookings")

def load_payments(session):
    df = read_sheet("Payments")
    objects = [Payment(payment_id=clean_id(row["payment_id"]), booking_id=clean_id(row["booking_id"]), user_id=clean_id(row["user_id"]), transaction_status="Success") for _, row in df.iterrows()]
    batch_upsert(session, objects, "Payments")

def load_seats(session):
    df = read_sheet("Seats")
    objects = []
    for _, row in df.iterrows():
        b_id = clean_id(row.get("booking_id"))
        objects.append(Seat(
            seat_id=clean_id(row["seat_id"]),
            booking_id=b_id if b_id else None,
            screen_id=clean_id(row["screen_id"]),
            seat_number=clean(row.get("seat_number")),
            status=clean(row.get("status")) or "Available"
        ))
    batch_upsert(session, objects, "Seats")

def load_reviews(session):
    df = read_sheet("Reviews")
    objects = [Review(review_id=clean_id(row["review_id"]), user_id=clean_id(row["user_id"]), movie_id=clean_id(row["movie_id"]), rating=float(row["rating"]) if clean(row.get("rating")) else 5.0) for _, row in df.iterrows()]
    batch_upsert(session, objects, "Reviews")

def main():
    app = create_app()
    with app.app_context():
        session = db.session
        print("\n🚀 Starting FULL data seed...\n")
        load_users(session)
        load_movies(session)
        load_theaters(session)
        load_screens(session)
        load_shows(session)
        load_bookings(session)
        load_payments(session)
        load_seats(session)
        load_reviews(session)
        print("✅ Seed complete!")

if __name__ == "__main__":
    main()

    