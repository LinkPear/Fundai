"""
backfill_where_to_get.py — one-off backfill of the new cards.where_to_get column.

Why this exists:
  where_to_get was added after ~1700 cards were already scraped, so every
  existing row is NULL. sync.py can't fill them in — it's diff-aware and only
  scrapes cards MISSING from the DB, and all of these already exist. This
  script revisits every card's detail page and writes ONLY where_to_get.

What it does NOT do (deliberately):
  - No image download / re-host (scrape_card_detail(..., skip_image=True)),
    which is what makes a normal scrape slow — this pass is ~half the time.
  - No writes to any other column. The UPDATE below touches where_to_get and
    nothing else, so a re-run can never clobber names, stats, effects, etc.

Matching:
  Each card row is keyed the same way upsert_card keys it —
  (set_id, card_code, rarity, alt_art) — so multi-printing cards (booster +
  promo variants of the same card_code) each get their own correct value.

Usage:
  python backfill_where_to_get.py                # all sets
  python backfill_where_to_get.py GD02 PROMOTION_CARD   # only these set_codes

Idempotent: safe to re-run (e.g. to pick up sets that errored out).
"""

import asyncio
import sys

from playwright.async_api import async_playwright

from scraper import SETS, dismiss_cookie_banner, get_card_ids_for_set, scrape_card_detail
from db import get_connection, upsert_set


def update_where_to_get(conn, set_id, card):
    """Write only where_to_get for the row matching this printing's unique key.

    Returns the number of rows updated (0 if the printing isn't in the DB yet
    — that's a job for sync.py, not this backfill).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cards
               SET where_to_get = %(where_to_get)s
             WHERE set_id   = %(set_id)s
               AND card_code = %(card_code)s
               AND rarity    = %(rarity)s
               AND alt_art   = %(alt_art)s
            """,
            {
                "where_to_get": card["where_to_get"],
                "set_id": set_id,
                "card_code": card["card_code"],
                "rarity": card["rarity"],
                "alt_art": card["alt_art"],
            },
        )
        return cur.rowcount


async def backfill(set_codes=None):
    conn = get_connection()
    target_sets = [s for s in SETS if set_codes is None or s["set_code"] in set_codes]

    updated_total = 0
    filled_total = 0   # rows where the scraped value was non-empty
    missing_total = 0  # printings on the site not yet in our DB
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for set_data in target_sets:
            set_code = set_data["set_code"]
            print(f"\nBackfilling {set_code} — {set_data['name']}")
            try:
                set_id = upsert_set(conn, set_data)
                conn.commit()

                card_ids = await get_card_ids_for_set(page, set_code, set_data.get("data_val"))

                for i, card_id in enumerate(card_ids):
                    print(f"  [{i + 1}/{len(card_ids)}] {card_id}")
                    try:
                        card = await scrape_card_detail(page, card_id, skip_image=True)
                        rows = update_where_to_get(conn, set_id, card)
                        conn.commit()
                        if rows == 0:
                            missing_total += 1
                            print(f"    (not in DB yet — skipped: {card['card_code']} "
                                  f"{card['rarity']}{card['alt_art']})")
                        else:
                            updated_total += rows
                            if card["where_to_get"]:
                                filled_total += rows
                            print(f"    {card['card_code']} {card['rarity']}{card['alt_art']} "
                                  f"-> where_to_get = {card['where_to_get'] or '(blank)'}")
                    except Exception as e:
                        conn.rollback()
                        msg = f"Error on {card_id} in {set_code}: {e}"
                        print(f"    ERROR: {msg}")
                        errors.append(msg)

            except Exception as e:
                conn.rollback()
                msg = f"Error processing set {set_code}: {e}"
                print(f"  ERROR: {msg}")
                errors.append(msg)

        await browser.close()

    conn.close()

    print("\n===== BACKFILL SUMMARY =====")
    print(f"Rows updated:            {updated_total}")
    print(f"  of which non-blank:    {filled_total}")
    print(f"Printings not yet in DB: {missing_total}")
    print(f"Errors:                  {len(errors)}")
    for e in errors:
        print(f"  - {e}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    codes = sys.argv[1:] or None
    asyncio.run(backfill(codes))
