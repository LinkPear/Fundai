"""
backfill_links.py — one-off backfill of link_conditions for trait links.

Why this exists:
  Until now scraper.py only kept the [Pilot Name] part of a card's Link line,
  so trait links such as "(Titans) Trait" were dropped and those units looked
  like they had no Link at all. scraper.py now keeps both (see parse_links),
  but sync.py only scrapes cards MISSING from the DB, so existing rows never get
  re-read. This script revisits every card's detail page and rewrites ONLY that
  card's link_conditions rows.

What it does NOT do (deliberately):
  - No image download / re-host (skip_image=True).
  - No writes to the cards table or any other table.

Matching: same printing key as upsert_card — (set_id, card_code, rarity, alt_art).

Usage:
  python backfill_links.py                 # all sets
  python backfill_links.py GD02 ST04       # only these set_codes

Idempotent: safe to re-run. Run export-cards.py afterwards to regenerate
cards.json (the GitHub Action does both).
"""

import asyncio
import sys

from playwright.async_api import async_playwright

from scraper import SETS, get_card_ids_for_set, scrape_card_detail
from db import get_connection, upsert_set


def replace_links(conn, set_id, card):
    """Rewrite link_conditions for the row(s) matching this printing.

    Returns the number of card rows touched (0 = printing not in the DB yet).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM cards
             WHERE set_id = %(set_id)s AND card_code = %(card_code)s
               AND rarity = %(rarity)s AND alt_art = %(alt_art)s
            """,
            {"set_id": set_id, "card_code": card["card_code"],
             "rarity": card["rarity"], "alt_art": card["alt_art"]},
        )
        ids = [r[0] if not isinstance(r, dict) else r["id"] for r in cur.fetchall()]
        for card_id in ids:
            cur.execute("DELETE FROM link_conditions WHERE card_id = %s", (card_id,))
            for link in card["links"]:
                cur.execute(
                    "INSERT INTO link_conditions (card_id, pilot_name) VALUES (%s, %s)",
                    (card_id, link),
                )
        return len(ids)


async def backfill(set_codes=None):
    conn = get_connection()
    target_sets = [s for s in SETS if set_codes is None or s["set_code"] in set_codes]

    updated = trait_links = missing = 0
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for set_data in target_sets:
            set_code = set_data["set_code"]
            print(f"\nBackfilling links for {set_code} — {set_data['name']}")
            try:
                set_id = upsert_set(conn, set_data)
                conn.commit()
                card_ids = await get_card_ids_for_set(page, set_code, set_data.get("data_val"))
                for i, card_id in enumerate(card_ids):
                    try:
                        card = await scrape_card_detail(page, card_id, skip_image=True)
                        rows = replace_links(conn, set_id, card)
                        conn.commit()
                        if rows == 0:
                            missing += 1
                            continue
                        updated += rows
                        if any(l.startswith("(") for l in card["links"]):
                            trait_links += rows
                        print(f"  [{i + 1}/{len(card_ids)}] {card['card_code']} "
                              f"{card['rarity']}{card['alt_art']} -> {card['links'] or '(no link)'}")
                    except Exception as e:
                        conn.rollback()
                        errors.append(f"{card_id} in {set_code}: {e}")
                        print(f"    ERROR: {errors[-1]}")
            except Exception as e:
                conn.rollback()
                errors.append(f"set {set_code}: {e}")
                print(f"  ERROR: {errors[-1]}")

        await browser.close()
    conn.close()

    print("\n===== LINK BACKFILL SUMMARY =====")
    print(f"Rows updated:              {updated}")
    print(f"  with a trait link:       {trait_links}")
    print(f"Printings not yet in DB:   {missing}")
    print(f"Errors:                    {len(errors)}")
    for e in errors:
        print(f"  - {e}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(backfill(sys.argv[1:] or None))
