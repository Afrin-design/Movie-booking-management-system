"""
scripts/run_brand_migration.py
──────────────────────────────
Run this ONCE after deploying the new code to apply the
brand-owner mapping schema changes to your PostgreSQL database.

Usage:
    cd /path/to/bms_24
    python scripts/run_brand_migration.py

It is idempotent — safe to run multiple times.
"""

import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database.db import db
from sqlalchemy import text


MIGRATION_SQL = """
-- 1. theater_brands table
CREATE TABLE IF NOT EXISTS theater_brands (
    id         SERIAL PRIMARY KEY,
    brand_name VARCHAR(100) NOT NULL UNIQUE,
    logo       VARCHAR(255),
    status     VARCHAR(20)  NOT NULL DEFAULT 'Active'
);

-- 2. Seed standard brands
INSERT INTO theater_brands (brand_name, status) VALUES
    ('PVR',       'Active'),
    ('INOX',      'Active'),
    ('Carnival',  'Active'),
    ('Cinepolis', 'Active'),
    ('Miraj',     'Active'),
    ('Wave',      'Active')
ON CONFLICT (brand_name) DO NOTHING;

-- 3. theaters.brand_id
ALTER TABLE theaters
    ADD COLUMN IF NOT EXISTS brand_id INTEGER
        REFERENCES theater_brands(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_theaters_brand_id ON theaters(brand_id);

-- 4. users.brand_id + users.status
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS brand_id INTEGER
        REFERENCES theater_brands(id) ON DELETE SET NULL;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'Active';
CREATE INDEX IF NOT EXISTS idx_users_brand_id ON users(brand_id);

-- 5. Auto-map theaters → brand by name
UPDATE theaters t
SET brand_id = b.id
FROM theater_brands b
WHERE t.brand_id IS NULL
  AND t.name ILIKE '%' || b.brand_name || '%';

-- 6. Map owner brand_id from their most-owned theater brand
WITH owner_brand AS (
    SELECT
        owner_id,
        brand_id,
        COUNT(*) AS cnt,
        ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY COUNT(*) DESC) AS rn
    FROM theaters
    WHERE owner_id IS NOT NULL AND brand_id IS NOT NULL
    GROUP BY owner_id, brand_id
)
UPDATE users u
SET brand_id = ob.brand_id
FROM owner_brand ob
WHERE ob.owner_id = u.user_id
  AND ob.rn = 1
  AND u.role = 'theater_owner';
"""


def run():
    app = create_app(os.environ.get("FLASK_ENV", "development"))
    with app.app_context():
        print("▶ Running brand-owner migration…")
        try:
            with db.engine.begin() as conn:
                for stmt in MIGRATION_SQL.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(text(stmt))
            print("✅ Migration complete.")

            # Quick stats
            with db.engine.connect() as conn:
                brands = conn.execute(text("SELECT COUNT(*) FROM theater_brands")).scalar()
                mapped_theaters = conn.execute(
                    text("SELECT COUNT(*) FROM theaters WHERE brand_id IS NOT NULL")
                ).scalar()
                mapped_owners = conn.execute(
                    text("SELECT COUNT(*) FROM users WHERE role='theater_owner' AND brand_id IS NOT NULL")
                ).scalar()

            print(f"\n📊 Post-migration stats:")
            print(f"   Brands created : {brands}")
            print(f"   Theaters mapped: {mapped_theaters}")
            print(f"   Owners mapped  : {mapped_owners}")

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    run()
