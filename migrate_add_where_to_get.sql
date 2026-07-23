-- Migration: add where_to_get to cards
--
-- The card detail page exposes a "Where to get it" field that names the
-- specific product a printing comes from (e.g. "Store Tournament Winner
-- Pack 04"). It's printing-specific: the same card_code can have multiple
-- rows (booster + promo variants), each with a different source. Nothing in
-- the schema captured it — promo printings were collapsed into the generic
-- PROMOTION_CARD set with no record of the actual distribution product.
--
-- Fix: store the raw "Where to get it" string per card row. Scraper reads it
-- from the dl.dataBox dt/dd pairs (label "where to get it") and upserts it.
--
-- Safe to run multiple times (IF NOT EXISTS guard).

BEGIN;

ALTER TABLE cards ADD COLUMN IF NOT EXISTS where_to_get TEXT;

COMMIT;
