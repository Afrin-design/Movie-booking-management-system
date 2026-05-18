import pandas as pd
from sqlalchemy import create_engine, text
import os

# 1. Database Connection (Make sure to put your real password back in!)
DB_URI = 'postgresql://postgres:Afrin%409346@localhost:5432/movie_db'
engine = create_engine(DB_URI)

excel_file = 'CineHub_Dataset.xlsx'

print(f"🚀 Starting direct data dump from {excel_file}...")

if os.path.exists(excel_file):
    try:
        print("Reading the Excel file (this might take 10-20 seconds)...")
        all_sheets = pd.read_excel(excel_file, sheet_name=None, engine='openpyxl')
        
        # 2. Safely wipe out the old tables and their foreign keys first!
        print("Clearing old tables and removing strict constraints...")
        with engine.begin() as conn:
            for sheet_name in all_sheets.keys():
                table_name = sheet_name.lower()
                # CASCADE forces the database to let go of the old tables
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
        
        # 3. Dump the new data
        for sheet_name, df in all_sheets.items():
            table_name = sheet_name.lower()
            print(f"Loading tab '{sheet_name}' into table '{table_name}'...")
            
            # Now it will create the tables fresh without crashing
            df.to_sql(table_name, con=engine, if_exists='replace', index=False)
            
            print(f"  ✅ Success: {len(df)} rows loaded into '{table_name}'.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print(f"❌ ERROR: {excel_file} is not in this folder!")

print("🎉 Data dump completely finished!")