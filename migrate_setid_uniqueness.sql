-- Migration: fix cards uniqueness to account for cross-set reprints
--
-- Problem: UNIQUE(card_code, rarity, alt_art) doesn't include set_id, so
-- when the same physical card is reprinted in a different set, the scraper's
-- ON CONFLICT upsert silently overwrote the existing row's set_id instead of
-- inserting a new row for the new set.
--
-- Fix: widen the uniqueness constraint to UNIQUE(set_id, card_code, rarity, alt_art)
-- so reprints across sets coexist as separate rows.
--
-- Safe to run multiple times (uses IF EXISTS / IF NOT EXISTS guards).

BEGIN;

-- Drop the old constraint. Name is Postgres's default auto-generated name
-- for UNIQUE(card_code, rarity, alt_art) on the cards table.
ALTER TABLE cards DROP CONSTRAINT IF EXISTS cards_card_code_rarity_alt_art_key;

-- Add the corrected constraint.
ALTER TABLE cards ADD CONSTRAINT cards_set_id_card_code_rarity_alt_art_key
    UNIQUE (set_id, card_code, rarity, alt_art);

COMMIT;
