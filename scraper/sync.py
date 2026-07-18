"""
sync.py — diff-aware wrapper around scraper.py + export-cards.py

Meant to be run on a schedule (see .github/workflows/scrape-and-export.yml).
Instead of re-scraping every card on every run, it:

  1. Checks the live site's set filter list for any set codes we don't
     already know about (a brand new set Bandai has added).
  2. For every known set (plus any newly-discovered ones), fetches the
     live card list and compares it against what's already in the
     database — only cards that are missing get their detail page
     scraped and written.
  3. If anything new was found, re-runs export-cards.py to regenerate
     cards.json so the app's next fetch picks up the changes.
  4. Exits with a non-zero status if any errors occurred, so GitHub
     Actions marks the run as failed and sends its built-in failure
     notification.

Run manually with:  python sync.py
"""

import asyncio
import os
import re
import subprocess
import sys

from playwright.async_api import async_playwright

from scraper import (
    SETS,
    BASE_URL,
    dismiss_cookie_banner,
    get_card_ids_for_set,
    scrape_card_detail,
)
from db import (
    get_connection,
    upsert_set,
    upsert_card,
    insert_traits,
    insert_zones,
    insert_link_conditions,
)

# Identity for "have we seen this filter entry before" is the site's own
# data-val id, not a human set_code — data_val is an opaque numeric string
# (e.g. "616101") that never matched the old bracket-code-shaped regex this
# function used to filter on, which meant this new-set detection never
# actually fired for anything, known or new. See v1.7 roadmap notes.
KNOWN_DATA_VALS = {s["data_val"] for s in SETS if s.get("data_val")}
BRACKET_CODE_PATTERN = re.compile(r"\[([A-Z0-9]{2,6})\]")


def guess_product_type(set_code):
    """Best-effort product type for a set we've never seen before."""
    if set_code.startswith("GD"):
        return "booster"
    if set_code.startswith("ST"):
        return "starter"
    if set_code.startswith("EB"):
        return "extra"
    return "unknown"


def derive_set_code(text):
    """Human-readable set_code from a filter link's visible text.

    Prefers a bracketed code (e.g. "Deck Build Box Freedom Ascension [SC01]"
    -> "SC01"), matching the convention already used for GDxx/STxx/EBxx.
    Several site entries have no bracket at all (e.g. "Promotion card") --
    those fall back to an upper-snake-case slug of the full label, so they
    still get a stable, readable code instead of being silently dropped.
    """
    match = BRACKET_CODE_PATTERN.search(text)
    if match:
        return match.group(1)
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


async def get_live_set_filters(page):
    """Scrape the "Included In" filter dropdown on the main cards page.
    Returns a list of {"data_val", "code", "text"} dicts, one per entry
    (the "ALL" reset link and any entry with an empty data-val are skipped).
    """
    await page.goto(BASE_URL, wait_until="networkidle")
    await dismiss_cookie_banner(page)

    seen = {}
    links = await page.locator("a[data-val]").all()
    for link in links:
        data_val = await link.get_attribute("data-val")
        if not data_val:
            continue
        data_val = data_val.strip()
        text = (await link.inner_text()).strip()
        if not text or text.lower().startswith("included in"):
            continue
        # The dropdown's DOM is duplicated (collapsed header + expanded
        # panel) -- dedup by data_val, which is stable across both copies.
        seen[data_val] = text

    return [
        {"data_val": data_val, "code": derive_set_code(text), "text": text}
        for data_val, text in seen.items()
    ]


def site_id_for(card_code, alt_art, image_url):
    """Reconstruct the site's listing-page id (e.g. GD01-001_p1) for an
    already-stored card, to diff against the live listing page's ids.

    NOTE: the site does NOT map alt_art symbol -> suffix 1:1, and a
    reprint's suffix isn't limited to alt-art variants either — even a
    plain base-rarity (alt_art == "") reprint gets its own running
    "_pN" suffix once the same card_code has appeared more than once.
    The only reliable source is the real filename stem in the stored
    image_url (same field export-cards.py's derive_code() reads), so
    that lookup must run regardless of alt_art. The alt_art-based
    mapping below is only a last-resort fallback for rows scraped
    before image_url was reliably captured.
    """
    match = re.search(r'/([^/]+)\.webp', image_url or '')
    if match:
        return match.group(1).split('?')[0]

    if not alt_art:
        return card_code
    if alt_art == "+":
        return f"{card_code}_p1"
    if alt_art == "++":
        return f"{card_code}_p2"
    if alt_art == "SP":
        return f"{card_code}_SP"
    return card_code


def get_existing_card_codes(conn, set_id):
    """Site-style ids (e.g. GD01-001, GD01-001_p1) already stored for this
    set, used for diffing against the live listing page's ids.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT card_code, alt_art, image_url FROM cards WHERE set_id = %s", (set_id,))
        return {
            site_id_for(code, alt_art, image_url)
            for code, alt_art, image_url in cur.fetchall()
        }


async def sync():
    conn = get_connection()
    new_cards_total = 0
    new_sets_found = []
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # --- 1. New set detection ---
        print("Checking site for set codes we don't know about yet...")
        try:
            live_filters = await get_live_set_filters(page)
        except Exception as e:
            print(f"  WARNING: could not read the live set filter list: {e}")
            live_filters = []

        target_sets = list(SETS)  # start from the known roster in scraper.py

        for f in live_filters:
            if f["data_val"] not in KNOWN_DATA_VALS:
                print(f'  NEW SET DETECTED: {f["code"]} — "{f["text"]}" (data-val={f["data_val"]}, not in scraper.py SETS list)')
                new_sets_found.append(f["code"])
                target_sets.append(
                    {
                        "set_code": f["code"],
                        "name": f["text"],
                        "product_type": guess_product_type(f["code"]),
                        "release_date": None,
                        "data_val": f["data_val"],
                    }
                )

        # --- 2. Per-set diff + scrape ---
        for set_data in target_sets:
            set_code = set_data["set_code"]
            print(f"\nChecking {set_code} — {set_data['name']}")
            try:
                set_id = upsert_set(conn, set_data)
                conn.commit()

                live_ids = await get_card_ids_for_set(page, set_code, set_data.get("data_val"))
                existing_codes = get_existing_card_codes(conn, set_id)
                new_ids = [cid for cid in live_ids if cid not in existing_codes]

                if not new_ids:
                    print(f"  No new cards for {set_code} ({len(live_ids)} live, {len(existing_codes)} in DB)")
                    continue

                print(f"  {len(new_ids)} new card(s) found for {set_code}: {new_ids}")

                for i, card_id in enumerate(new_ids):
                    print(f"  [{i + 1}/{len(new_ids)}] scraping {card_id}")
                    try:
                        card = await scrape_card_detail(page, card_id)
                        card["set_id"] = set_id
                        card_db_id = upsert_card(conn, card)
                        insert_zones(conn, card_db_id, card["zones"])
                        insert_traits(conn, card_db_id, card["traits"])
                        insert_link_conditions(conn, card_db_id, card["links"])
                        conn.commit()
                        new_cards_total += 1
                        print(f"    Saved: {card['card_code']} {card['rarity']}{card['alt_art']} — {card['name']}")
                    except Exception as e:
                        conn.rollback()
                        msg = f"Error scraping card {card_id} in {set_code}: {e}"
                        print(f"    ERROR: {msg}")
                        errors.append(msg)

            except Exception as e:
                conn.rollback()
                msg = f"Error processing set {set_code}: {e}"
                print(f"  ERROR: {msg}")
                errors.append(msg)

        await browser.close()

    conn.close()

    # --- 3. Re-export cards.json only if something actually changed ---
    if new_cards_total > 0:
        print(f"\n{new_cards_total} new card(s) total — regenerating cards.json...")
        export_script = os.path.join(os.path.dirname(__file__), "export-cards.py")
        result = subprocess.run([sys.executable, export_script])
        if result.returncode != 0:
            errors.append("export-cards.py failed — cards.json was not regenerated")
    else:
        print("\nNo new cards found across any set — cards.json left unchanged.")

    # --- 4. Summary ---
    print("\n===== SYNC SUMMARY =====")
    print(f"New cards added: {new_cards_total}")
    print(f"New sets detected: {new_sets_found if new_sets_found else 'none'}")
    print(f"Errors: {len(errors)}")
    for e in errors:
        print(f"  - {e}")

    if errors:
        # Non-zero exit -> GitHub Actions marks the job failed -> triggers
        # its built-in failure notification email automatically.
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(sync())
