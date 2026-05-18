import pandas as pd
import os

csv_files = [
    'users.csv', 'movies.csv', 'theaters.csv', 'screens.csv', 
    'shows.csv', 'bookings.csv', 'payments.csv', 'seats.csv', 'reviews.csv'
]

print("🔍 Checking your CSV files...\n")

for file in csv_files:
    if os.path.exists(file):
        try:
            df = pd.read_csv(file)
            print(f"✅ {file}: Contains exactly {len(df)} rows of data.")
        except pd.errors.EmptyDataError:
            print(f"⚠️ {file}: File exists but is COMPLETELY EMPTY (no data).")
        except Exception as e:
            print(f"❌ {file}: Error reading file - {e}")
    else:
        print(f"❌ {file}: FILE NOT FOUND in this folder.")