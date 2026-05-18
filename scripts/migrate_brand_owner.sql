-- ============================================================
-- Migration: Brand-Owner Mapping System
-- Run this on your PostgreSQL database ONCE.
-- ============================================================

BEGIN;

-- ── 1. Create theater_brands table ───────────────────────────
CREATE TABLE IF NOT EXISTS theater_brands (
    id         SERIAL PRIMARY KEY,
    brand_name VARCHAR(100) NOT NULL UNIQUE,
    logo       VARCHAR(255),
    status     VARCHAR(20)  NOT NULL DEFAULT 'Active'
);

-- ── 2. Seed well-known brands ────────────────────────────────
INSERT INTO theater_brands (brand_name, status) VALUES
    ('PVR',       'Active'),
    ('INOX',      'Active'),
    ('Carnival',  'Active'),
    ('Cinepolis', 'Active'),
    ('Miraj',     'Active'),
    ('Wave',      'Active')
ON CONFLICT (brand_name) DO NOTHING;

-- ── 3. Add brand_id to theaters ──────────────────────────────
ALTER TABLE theaters
    ADD COLUMN IF NOT EXISTS brand_id INTEGER
        REFERENCES theater_brands(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_theaters_brand_id ON theaters(brand_id);

-- ── 4. Add brand_id + status to users ────────────────────────
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS brand_id INTEGER
        REFERENCES theater_brands(id) ON DELETE SET NULL;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'Active';

CREATE INDEX IF NOT EXISTS idx_users_brand_id ON users(brand_id);

-- ── 5. Auto-map brand_id on theaters by name pattern ─────────
--   Matches theaters whose name contains the brand string.
--   Adjust ILIKE patterns to match your actual data.
UPDATE theaters t
SET brand_id = b.id
FROM theater_brands b
WHERE t.brand_id IS NULL
  AND t.name ILIKE '%' || b.brand_name || '%';

-- ── 6. Map owner brand_id from their most-owned theater brand ─
--   Each owner gets the brand they own the most theaters in.
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

COMMIT;

-- ── 7. Useful verification queries ───────────────────────────
-- SELECT brand_name, COUNT(*) AS theater_count
--   FROM theater_brands tb
--   JOIN theaters t ON t.brand_id = tb.id
--   GROUP BY brand_name ORDER BY theater_count DESC;
--
-- SELECT u.name, u.email, tb.brand_name,
--        COUNT(t.theater_id) AS theater_count
--   FROM users u
--   JOIN theater_brands tb ON tb.id = u.brand_id
--   LEFT JOIN theaters t ON t.brand_id = tb.id
--   WHERE u.role = 'theater_owner'
--   GROUP BY u.user_id, tb.brand_name ORDER BY u.name;
