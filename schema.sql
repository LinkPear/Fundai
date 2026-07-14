CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    product_type TEXT NOT NULL,
    release_date DATE,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id UUID NOT NULL REFERENCES sets(id),
    card_code TEXT NOT NULL,
    name TEXT NOT NULL,
    card_type TEXT NOT NULL,
    color TEXT,
    level INT,
    cost INT,
    ap INT,
    hp INT,
    effect_text TEXT,
    source_title TEXT,
    image_url TEXT,
    rarity TEXT NOT NULL,
    alt_art TEXT NOT NULL DEFAULT '',
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(set_id, card_code, rarity, alt_art)
);

CREATE TABLE IF NOT EXISTS traits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    card_id UUID NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    trait TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    card_id UUID NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    zone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS link_conditions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    card_id UUID NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    pilot_name TEXT NOT NULL
);
