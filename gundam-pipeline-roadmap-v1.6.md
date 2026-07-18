# Gundam TCG pipeline — project roadmap
**Version:** 1.6
**Last updated:** 2026-07-17
**Status:** Session 5 complete — fixed LinkPear's image-loading bug (Bandai CORP header blocked cross-origin loads) by re-hosting card images in Supabase Storage. Backfill run for all 1,342 existing cards: 0 failures. `cards.json` regenerated, committed, and pushed (`893de00`). LinkPear re-synced and confirmed working end-to-end.

---

## Project overview

A backend pipeline that scrapes the official Bandai Gundam Card Game website for card data and exposes it as a static JSON file hosted on GitHub for use in a Next.js TCG collection tracker app (LinkPear).

**Source:** https://www.gundam-gcg.com/en/cards/
**Card data hosting:** GitHub (static JSON — free, no server needed)
**Card image hosting:** Supabase Storage (`card-images` bucket, public, webp-only) ← new this session
**Database hosting:** Supabase (free tier)
**Stack:** Python · Playwright · PostgreSQL (Supabase) · Supabase Storage · GitHub Actions

---

## This session: fixing the LinkPear image-loading bug

### The bug

`image_url` stored Bandai's own CDN URL directly, and export-cards.py put that URL straight into `cards.json`'s `imageSmall`/`imageLarge`. Bandai's CDN sends `Cross-Origin-Resource-Policy: same-site` on every image response — a browser-enforced policy that blocks a different-origin page (LinkPear) from loading the image at all. Browsers threw `ERR_BLOCKED_BY_RESPONSE.NotSameSite`. Not fixable from LinkPear's side; had to be fixed at the source.

### The fix

- New `scraper/image_host.py`: downloads each card image from Bandai (with a `Referer: https://www.gundam-gcg.com/` header — Bandai's CDN gates on it) and re-uploads it to a new public Supabase Storage bucket, `card-images` (webp-only, 5 MB file size limit). Returns the public hosted URL, or `None` on any failure.
- New `hosted_image_url` column on `cards` (migration: `migrate_add_hosted_image_url.sql`). **`image_url` itself is untouched** — it still holds Bandai's own path and is still the only reliable source for the true site listing-page id that `derive_code()` / `site_id_for()` depend on. The two columns serve different purposes and must not be conflated.
- `scraper.py`'s `scrape_card_detail()` now calls `download_and_host_image()` right after scraping `image_url`, so both `scraper.py` (full run) and `sync.py` (diff-aware, new cards only) pick up hosted images automatically with no extra plumbing.
- `db.py`'s `upsert_card` persists `hosted_image_url`, using `COALESCE(EXCLUDED.hosted_image_url, cards.hosted_image_url)` on conflict so a failed re-download never overwrites a previously-good hosted URL with `NULL`.
- `export-cards.py` now sets `imageSmall`/`imageLarge` from `hosted_image_url`, falling back to the old Bandai-URL derivation only for rows that predate this fix and haven't been backfilled yet.
- New one-off `scraper/backfill_images.py`: `sync.py` only ever scrapes *new* cards, so it will never touch the 1,342 existing rows (all NULL `hosted_image_url`). This script finds every card missing a hosted image, backfills it, and re-exports `cards.json`. **Must be run once, manually, before LinkPear's images will actually work for existing cards.**
- `requirements.txt`: added `requests` (image download/upload — kept it to a plain HTTP call against the Storage REST API rather than pulling in the full `supabase-py` SDK, matching the existing minimal-dependency style).
- `.env.example` / `.env`: added `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (service_role, not anon — needed to bypass RLS on upload; server-side only).
- `.github/workflows/scrape-and-export.yml`: passes the two new secrets through to the `sync.py` step. **The `SUPABASE_SERVICE_ROLE_KEY` GitHub Actions secret still needs to be added manually** (not settable via the Supabase MCP for security reasons — copy it from Project Settings > API > service_role secret).

### Why Supabase Storage over alternatives

Already part of the stack (same Supabase project as the DB), free-tier storage (1 GB) comfortably covers ~1,342 small webp thumbnails, and a public bucket serves plain HTTPS with no CORP restriction — satisfying all three of the brief's requirements without adding a new vendor. Considered committing images into the GitHub repo instead (served via `raw.githubusercontent.com`), but that bloats repo history with binary blobs on every re-scrape; rejected.

---

## Key design decisions (locked)

- Every card variant (base, SP, +, ++) is its own row — not a nested object
- Unique key per card: **`(set_id, card_code, rarity, alt_art)`** — set_id is part of the key
- `rarity` and `alt_art` are stored as separate columns — `alt_art` is empty string `""` for base cards (not null)
- **`alt_art` and the site's `_pN` reprint suffix are independent axes** — never assume a 1:1 mapping. Always derive the true site id from `image_url`, only falling back to the symbolic `alt_art` mapping if `image_url` is missing.
- `zones`, `traits`, and `link_conditions` are child tables (multi-value fields, filterable)
- `image_url` stores the Bandai CDN URL and is **never** repurposed to point at our hosted copy — it's the only reliable source for the true site listing-page id. `hosted_image_url` is the separate, LinkPear-facing field. ← updated this session
- Card images are downloaded once (at scrape time, or via the one-off backfill for pre-existing rows) and re-hosted in Supabase Storage — never served to the browser from Bandai's CDN directly. ← new this session
- Hosted image filenames mirror Bandai's own filename stem exactly (e.g. `GD01-001_p1.webp`), so the mapping between `image_url` and `hosted_image_url` stays derivable and consistent.
- `scraped_at` on both `sets` and `cards` for audit trail and diff logic
- Scraper uses Playwright (site is JS-rendered)
- **CI runner pinned to `ubuntu-22.04`, not `ubuntu-latest`** — avoids Playwright/Ubuntu-noble `libasound2` package-rename breakage
- R-series resource cards (R-001 through R-009) are set-specific collectibles with unique artwork per set — stored as regular cards
- Card list uses `data-src="detail.php?detailSearch=GD01-001"` attributes — scraped directly
- Detail page selectors: `.cardNo`, `.rarity`, `h1.cardName`, `dl.dataBox` with `dt.dataTit` / `dd.dataTxt`
- Railway hosting scrapped — static JSON on GitHub instead
- Exported `id` field is set-qualified: `f"{set_code}-{code}"` — guarantees uniqueness across reprints
- User data (collections, decks, auth) stays in LinkPear's own backend — out of scope for this pipeline
- Cards legitimately reprint across sets, sometimes 2–3 times
- GitHub PATs (classic) need the **`workflow`** scope to push changes to `.github/workflows/*.yml` files

---

## Files changed/produced this session

- `image_host.py` (new) — download-from-Bandai + upload-to-Supabase-Storage helper
- `backfill_images.py` (new) — one-off backfill for the 1,342 existing cards
- `migrate_add_hosted_image_url.sql` (new) — adds `cards.hosted_image_url`
- `schema.sql` — added `hosted_image_url TEXT` to `cards`
- `scraper.py` — `scrape_card_detail()` now hosts the image and returns `hosted_image_url`
- `db.py` — `upsert_card` persists `hosted_image_url` with COALESCE-on-conflict
- `export-cards.py` — `imageSmall`/`imageLarge` now sourced from `hosted_image_url`
- `requirements.txt` — added `requests`
- `.env.example`, `.env` — added `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `.github/workflows/scrape-and-export.yml` — passes the two new secrets to `sync.py`

**Live infra changes (via Supabase MCP, already applied):** `card-images` Storage bucket created (public, webp-only, 5 MB limit); `hosted_image_url` column added to `cards` in the live DB.

---

## Next steps

1. **Done this session:** `SUPABASE_SERVICE_ROLE_KEY` added to local `.env` and as a GitHub Actions secret; `backfill_images.py` run (1,342/1,342, 0 failures); `cards.json` committed and pushed (`893de00`); LinkPear re-synced (`wipe-cards.ts` + `sync-gundam.ts`) and confirmed images now load.
2. **Housekeeping still open:** the actual code for this fix (`image_host.py`, `backfill_images.py`, updated `scraper.py`/`db.py`/`export-cards.py`, `schema.sql`, the new migration file, `requirements.txt`, `.env.example`, and the workflow YAML) is still sitting as **uncommitted local changes** — only `cards.json` and this roadmap doc have been pushed so far. Until those files are committed and pushed, the GitHub Actions robot will keep running the *old* scraper code on its Monday/Thursday schedule — meaning the next new card it finds (e.g. GD05) would go right back to storing Bandai's raw, blocked image URL, silently undoing this fix. **Commit and push everything before the next scheduled run.**
3. **GD05 (Freedom Ascension, releases 2026-07-24)** — still not live on the site as of this session; revisit after the release date. Once the code above is pushed, `sync.py`'s new-card detection will pick it up and route its images through the new hosting path automatically — no manual backfill needed for future sets.
4. **Verify GitHub Actions' failure-email alerting actually fires** — still unverified from Session 4.

---

## Sets to scrape (as of 2026-07-14, unchanged this session)

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

**Total: 1,342 cards. All still need the one-off image backfill (see Next steps).**

---

## Versioning convention

When this document is updated, increment the version in the filename and the header:
- `gundam-pipeline-roadmap-v1.0.md` → planning complete
- `gundam-pipeline-roadmap-v1.1.md` → after session 1
- `gundam-pipeline-roadmap-v1.2.md` → after session 2
- `gundam-pipeline-roadmap-v1.3.md` → mid-session 3, database migrated to Supabase, automation built, cross-set reprint bug discovered and documented
- `gundam-pipeline-roadmap-v1.4.md` → session 3 complete: reprint bug fixed, sync.py diffing bug fixed
- `gundam-pipeline-roadmap-v1.5.md` → session 4 complete: committed & pushed, GitHub Actions verified green end-to-end, dead `asyncio` dependency removed
- `gundam-pipeline-roadmap-v1.6.md` → session 5 complete: fixed LinkPear image-loading bug via Supabase Storage re-hosting; backfill for existing 1,342 cards still pending ← current
- `gundam-pipeline-roadmap-v2.0.md` → major scope change
