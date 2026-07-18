-- Migration: add hosted_image_url to cards
--
-- Problem: image_url stores Bandai's own CDN URL. Bandai's CDN sends
-- `Cross-Origin-Resource-Policy: same-site` on every image response, which
-- browsers use to block cross-origin loads. LinkPear (a different origin)
-- gets ERR_BLOCKED_BY_RESPONSE.NotSameSite trying to load these images.
--
-- Fix: download each card image during scrape (with a Referer header, which
-- Bandai's CDN requires) and re-host it in our own Supabase Storage bucket
-- (`card-images`, public, no CORP restriction). hosted_image_url stores that
-- URL; export-cards.py uses it for imageSmall/imageLarge instead of the
-- Bandai URL.
--
-- image_url is left untouched — it's still the only reliable source for the
-- true site listing-page id (see derive_code() in export-cards.py and
-- site_id_for() in sync.py), so it must keep pointing at Bandai's own path.
--
-- Safe to run multiple times (IF NOT EXISTS guard).

BEGIN;

ALTER TABLE cards ADD COLUMN IF NOT EXISTS hosted_image_url TEXT;

COMMIT;
