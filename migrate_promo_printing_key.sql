-- migrate_promo_printing_key.sql
--
-- Fix: distinct promo printings of the same card_code at the same rarity/alt_art
-- were silently overwriting each other.
--
-- A single card in the Promotion category often has several distinct promo
-- printings that share the same rarity and alt_art and differ ONLY by
-- "where to get it" — e.g. GD02-029 exists as both "Store Tournament
-- Participant Pack 02" and "Booster Release Event" at rarity C. The old key
-- UNIQUE(set_id, card_code, rarity, alt_art) did not include where_to_get, so
-- the second printing collided with the first and last-write-won on upsert.
-- That is the same clobber bug the app fixed with the PromoPrice staging table;
-- the scraper pipeline never got the equivalent fix, so the losing printings
-- (mostly Participant Packs and event promos) were never stored — leaving their
-- JustTCG prices unmatchable.
--
-- Adding where_to_get to the printing identity lets every distinct printing keep
-- its own row. Each already has a distinct Bandai image filename (_pN), so the
-- downstream export/derive_code path assigns each a unique card id automatically.

-- 1. A key column can't be NULL. The scraper already writes '' when the field is
--    absent; normalize any legacy NULLs so the NOT NULL below is safe.
UPDATE cards SET where_to_get = '' WHERE where_to_get IS NULL;
ALTER TABLE cards ALTER COLUMN where_to_get SET DEFAULT '';
ALTER TABLE cards ALTER COLUMN where_to_get SET NOT NULL;

-- 2. Swap the uniqueness key. The old 4-column key is a strict subset of the new
--    5-column key, so every existing row is already unique under the new one and
--    ADD CONSTRAINT cannot fail on duplicates.
ALTER TABLE cards DROP CONSTRAINT cards_set_id_card_code_rarity_alt_art_key;
ALTER TABLE cards ADD CONSTRAINT cards_printing_key
    UNIQUE (set_id, card_code, rarity, alt_art, where_to_get);
