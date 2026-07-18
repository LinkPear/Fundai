# Gundam TCG pipeline — project roadmap
**Version:** 1.7
**Last updated:** 2026-07-18
**Status:** Session 6 complete — added 5 previously-untracked "Included In" filter entries and fixed the root-cause bug in `sync.py`'s new-set auto-detection that had silently swallowed all of them (and would have kept swallowing every future one). Local `sync.py` run confirmed clean: 367 new cards added across the 5 new entries, 0 errors, `cards.json` regenerated (1,700 cards total). Committed and pushed to `main` (`d582832..14d4ebb`).

---

## Project overview

A backend pipeline that scrapes the official Bandai Gundam Card Game website for card data and exposes it as a static JSON file hosted on GitHub for use in a Next.js TCG collection tracker app (LinkPear).

**Source:** https://www.gundam-gcg.com/en/cards/
**Card data hosting:** GitHub (static JSON — free, no server needed)
**Card image hosting:** Supabase Storage (`card-images` bucket, public, webp-only)
**Database hosting:** Supabase (free tier)
**Stack:** Python · Playwright · PostgreSQL (Supabase) · Supabase Storage · GitHub Actions

---

## This session: 5 untracked filter entries + a dead new-set-detection path

### How this started

Jordan spotted 5 entries in the site's "Included In" filter dropdown that weren't in our `SETS` roster: **Deck Build Box Freedom Ascension [SC01]**, **Other Product Card**, **Edition Beta**, **Basic Cards**, **Promotion card**.

### Root cause

`sync.py` already had new-set auto-detection (`get_live_set_filters()`), meant to catch exactly this. It read each filter link's `data-val` attribute and checked it against `SET_CODE_PATTERN = r"^[A-Z]{2,3}\d{2}$"` (a `GDxx`/`STxx`/`EBxx`-shaped regex), discarding anything that didn't match.

The bug: `data-val` is Bandai's own **opaque numeric package id** (e.g. `616101` for GD01), not a set code — the bracket code only ever appeared in the link's *visible text* ("Newtype Rising [GD01]"). The regex was being matched against the wrong field entirely, so it **never matched anything, known sets included** — new-set detection had silently done nothing since it was written; it just happened not to matter until Bandai added entries that don't fit the `SETS` roster's hardcoded, text-based click-matching either.

Confirmed via a one-off script (`scraper/debug_package_filters.py`, added this session) run against the live site:

| data-val | text |
|---|---|
| 616301 | Deck Build Box Freedom Ascension [SC01] |
| 616701 | Other Product Card |
| 616000 | Edition Beta |
| 616801 | Basic Cards |
| 616901 | Promotion card |

(Plus the 16 already-known entries, confirming their `data-val`s too — see `scraper.py`.)

### The fix

- **`scraper.py`**: every `SETS` entry now carries a `data_val` field (the site's real filter id). `get_card_ids_for_set()` now matches the filter link by exact `a[data-val="..."]` instead of a case-insensitive text substring — robust regardless of whether the label has a bracket code at all (several of the new entries don't).
- **`sync.py`**: `get_live_set_filters()` rewritten to key identity off `data_val` (via `KNOWN_DATA_VALS`, derived from `SETS`) instead of a regex over the wrong field. Human-readable `set_code`s for newly-discovered entries are derived by `derive_set_code()` — bracket code if present, else an upper-snake-case slug of the label — so future new entries surface as a readable `NEW SET DETECTED` log line instead of being silently dropped.
- Added the 5 new entries to `SETS`:

| set_code | name | product_type | data_val |
|---|---|---|---|
| SC01 | Deck Build Box Freedom Ascension | deck_build_box | 616301 |
| OTHER_PRODUCT_CARD | Other Product Card | other | 616701 |
| EDITION_BETA | Edition Beta | edition | 616000 |
| BASIC_CARDS | Basic Cards | basic | 616801 |
| PROMOTION_CARD | Promotion card | promo | 616901 |

- No `schema.sql` migration needed — `sets.product_type` is plain `TEXT`, no enum/check constraint, so the 5 new category strings above just work.

### Open question to watch

**SC01 (Deck Build Box Freedom Ascension)** may contain reprints of GD05 cards rather than new unique ones — same situation the cross-set reprint bug (Session 3) was built to handle. The existing `(set_id, card_code, rarity, alt_art)` unique key and the `alt_art`/site `_pN`-suffix independent-axis handling should cover this automatically since `set_id` differs from GD05's, but this needs a real scrape to confirm rather than assuming.

---

## Key design decisions (locked)

*(unchanged from v1.6 — see that doc for the full list: reprint handling, image hosting split between `image_url`/`hosted_image_url`, CI runner pin, etc.)*

- **New this session:** `SETS` entries also carry `data_val` — the site's own internal filter id — used for exact filter-link matching instead of fuzzy text matching. This is the correct long-term matching strategy; text-based `has_text` matching remains only as a fallback for callers without a `data_val`.
- **New this session:** identity for "is this set/category already known" is `data_val`, not any text-derived code — text labels and bracket codes are cosmetic/display only.

---

## Files changed/produced this session

- `scraper/scraper.py` — `SETS` entries gained `data_val`; 5 new entries added; `get_card_ids_for_set()` now matches by exact `data-val` attribute
- `scraper/sync.py` — `get_live_set_filters()` reworked to key off `data_val`; `derive_set_code()` added; new-set-detection loop updated accordingly
- `scraper/debug_package_filters.py` (new) — one-off diagnostic that dumps every `data-val`/text pair in the "Included In" dropdown; kept in the repo alongside the other `debug_*.py` scripts for the next time this needs re-checking

---

## Next steps

1. ~~Run `scraper.py`/`sync.py` locally for the 5 new entries~~ — done: 367 new cards, 0 errors, `cards.json` regenerated. No SC01/GD05 collision errors surfaced during the run.
2. ~~Commit and push~~ — done (`14d4ebb`). Hit a stale `.git/index.lock` along the way (same issue Session 4 saw once before — worth a permanent note: this keeps recurring, so if it happens a third time it may be worth figuring out what's actually leaving the lock behind rather than just clearing it each time).
3. **LinkPear (the app side)** now has 5 new set/category rows available via the API and `cards.json` — Jordan is heading over to confirm the integration picks them up cleanly (new `product_type` values it hasn't seen before: `deck_build_box`, `other`, `edition`, `basic`, `promo`).
4. **GD05 (Freedom Ascension, releases 2026-07-24)** — per v1.6, still needs to go live; revisit scrape status after the release date now just 6 days out.
5. **Verify GitHub Actions' failure-email alerting actually fires** — still unverified, carried over from Session 4.

---

## Sets to scrape (as of 2026-07-18)

| code | name | type | release | status |
|---|---|---|---|---|
| GD01 | Newtype Rising | booster | 2025-07-25 | ✅ scraped, clean |
| GD02 | Dual Impact | booster | TBC | ✅ scraped, clean |
| GD03 | Steel Requiem | booster | TBC | ✅ scraped, clean |
| GD04 | Phantom Aria | booster | 2026-04-24 | ✅ scraped, clean |
| GD05 | Freedom Ascension | booster | 2026-07-24 | ⏳ not yet released |
| ST01 | Heroic Beginnings | starter | TBC | ✅ scraped, clean |
| ST02 | Wings of Advance | starter | TBC | ✅ scraped, clean |
| ST03 | Zeon's Rush | starter | TBC | ✅ scraped, clean |
| ST04 | SEED Strike | starter | TBC | ✅ scraped, clean |
| ST05 | Iron Bloom | starter | TBC | ✅ scraped, clean |
| ST06 | Clan Unity | starter | TBC | ✅ scraped, clean |
| ST07 | Celestial Drive | starter | TBC | ✅ scraped, clean |
| ST08 | Flash of Radiance | starter | TBC | ✅ scraped, clean |
| ST09 | Destiny Ignition | starter | 2026-03-27 | ✅ scraped, clean |
| ST10 | Generation Pulse | starter | TBC | ✅ scraped, clean |
| EB01 | Eternal Nexus | extra | TBC | ✅ scraped, clean |
| SC01 | Deck Build Box Freedom Ascension | deck_build_box | TBC | ✅ scraped, clean |
| OTHER_PRODUCT_CARD | Other Product Card | other | — | ✅ scraped, clean |
| EDITION_BETA | Edition Beta | edition | — | ✅ scraped, clean |
| BASIC_CARDS | Basic Cards | basic | — | ✅ scraped, clean |
| PROMOTION_CARD | Promotion card | promo | — | ✅ scraped, clean |

**Total: 1,700 cards (367 added this session across the 5 new entries). Committed and pushed to `main`.**

---

## Versioning convention

When this document is updated, increment the version in the filename and the header:
- `gundam-pipeline-roadmap-v1.0.md` → planning complete
- `gundam-pipeline-roadmap-v1.1.md` → after session 1
- `gundam-pipeline-roadmap-v1.2.md` → after session 2
- `gundam-pipeline-roadmap-v1.3.md` → mid-session 3, database migrated to Supabase, automation built, cross-set reprint bug discovered and documented
- `gundam-pipeline-roadmap-v1.4.md` → session 3 complete: reprint bug fixed, sync.py diffing bug fixed
- `gundam-pipeline-roadmap-v1.5.md` → session 4 complete: committed & pushed, GitHub Actions verified green end-to-end, dead `asyncio` dependency removed
- `gundam-pipeline-roadmap-v1.6.md` → session 5 complete: fixed LinkPear image-loading bug via Supabase Storage re-hosting
- `gundam-pipeline-roadmap-v1.7.md` → session 6: added 5 untracked filter entries (SC01, Other Product Card, Edition Beta, Basic Cards, Promotion card); fixed dead new-set-detection regex bug in sync.py ← current
- `gundam-pipeline-roadmap-v2.0.md` → major scope change
