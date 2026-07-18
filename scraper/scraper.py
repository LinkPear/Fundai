import asyncio
import re
from playwright.async_api import async_playwright
from db import get_connection, upsert_set, upsert_card, insert_traits, insert_zones, insert_link_conditions
from image_host import download_and_host_image

BASE_URL = "https://www.gundam-gcg.com/en/cards/"
DETAIL_BASE = "https://www.gundam-gcg.com/en/cards/detail.php?detailSearch="

# "data_val" is the site's own internal id for each entry in the "Included In"
# filter dropdown (its data-val attribute) — captured via
# scraper/debug_package_filters.py. It's the only robust way to select the
# right filter link: unlike the visible label, it doesn't depend on the site
# keeping a "[GDxx]"-style bracket code in the text, which several entries
# (Edition Beta, Promotion card, Basic Cards, Other Product Card) don't have.
SETS = [
    {"set_code": "GD01", "name": "Newtype Rising",    "product_type": "booster", "release_date": "2025-07-25", "data_val": "616101"},
    {"set_code": "GD02", "name": "Dual Impact",       "product_type": "booster", "release_date": None,         "data_val": "616102"},
    {"set_code": "GD03", "name": "Steel Requiem",     "product_type": "booster", "release_date": None,         "data_val": "616103"},
    {"set_code": "GD04", "name": "Phantom Aria",      "product_type": "booster", "release_date": "2026-04-24", "data_val": "616104"},
    {"set_code": "GD05", "name": "Freedom Ascension", "product_type": "booster", "release_date": "2026-07-24", "data_val": "616105"},
    {"set_code": "ST01", "name": "Heroic Beginnings", "product_type": "starter", "release_date": None,         "data_val": "616001"},
    {"set_code": "ST02", "name": "Wings of Advance",  "product_type": "starter", "release_date": None,         "data_val": "616002"},
    {"set_code": "ST03", "name": "Zeon's Rush",       "product_type": "starter", "release_date": None,         "data_val": "616003"},
    {"set_code": "ST04", "name": "SEED Strike",       "product_type": "starter", "release_date": None,         "data_val": "616004"},
    {"set_code": "ST05", "name": "Iron Bloom",        "product_type": "starter", "release_date": None,         "data_val": "616005"},
    {"set_code": "ST06", "name": "Clan Unity",        "product_type": "starter", "release_date": None,         "data_val": "616006"},
    {"set_code": "ST07", "name": "Celestial Drive",   "product_type": "starter", "release_date": None,         "data_val": "616007"},
    {"set_code": "ST08", "name": "Flash of Radiance", "product_type": "starter", "release_date": None,         "data_val": "616008"},
    {"set_code": "ST09", "name": "Destiny Ignition",  "product_type": "starter", "release_date": "2026-03-27", "data_val": "616009"},
    {"set_code": "ST10", "name": "Generation Pulse",  "product_type": "starter", "release_date": None,         "data_val": "616010"},
    {"set_code": "EB01", "name": "Eternal Nexus",     "product_type": "extra",   "release_date": None,         "data_val": "616201"},
    # Added this session — previously invisible to sync.py's new-set detection
    # because it keyed off data-val against a bracket-code-shaped regex
    # (e.g. ^[A-Z]{2,3}\d{2}$), but data-val is an opaque numeric site id
    # (see comment above), not a set code. The regex never matched anything,
    # known or new, via that path — see gundam-pipeline-roadmap-v1.7.md.
    {"set_code": "SC01",               "name": "Deck Build Box Freedom Ascension", "product_type": "deck_build_box", "release_date": None, "data_val": "616301"},
    {"set_code": "OTHER_PRODUCT_CARD", "name": "Other Product Card",              "product_type": "other",           "release_date": None, "data_val": "616701"},
    {"set_code": "EDITION_BETA",       "name": "Edition Beta",                    "product_type": "edition",         "release_date": None, "data_val": "616000"},
    {"set_code": "BASIC_CARDS",        "name": "Basic Cards",                     "product_type": "basic",           "release_date": None, "data_val": "616801"},
    {"set_code": "PROMOTION_CARD",     "name": "Promotion card",                  "product_type": "promo",           "release_date": None, "data_val": "616901"},
]

def parse_int(val):
    try:
        return int(val.strip()) if val and val.strip() not in ("-", "") else None
    except:
        return None

def parse_alt_art(rarity_str):
    r = rarity_str.strip()
    if r.endswith("++"):
        return r[:-2].strip(), "++"
    elif r.endswith("+"):
        return r[:-1].strip(), "+"
    elif "SP" in r:
        return r.replace("SP", "").strip(), "SP"
    return r, ""

async def dismiss_cookie_banner(page):
    try:
        accept = page.locator("#onetrust-accept-btn-handler")
        if await accept.count() > 0:
            await accept.click()
            await page.wait_for_timeout(500)
    except:
        pass

async def get_card_ids_for_set(page, set_code, data_val=None):
    print(f"  Loading card list for {set_code}...")
    await page.goto(BASE_URL, wait_until="networkidle")
    await dismiss_cookie_banner(page)

    if data_val:
        # Exact match on the site's own filter id — robust regardless of how
        # the visible label is worded (several entries have no set-code
        # substring to match against at all, e.g. "Promotion card").
        set_link = page.locator(f'a[data-val="{data_val}"]')
    else:
        # Fallback for callers that don't have a data_val on hand yet.
        set_link = page.locator("a[data-val]").filter(has_text=set_code)

    if await set_link.count() == 0:
        print(f"  WARNING: No filter link found for {set_code}")
        return []

    await set_link.first.evaluate("el => el.click()")
    await page.wait_for_timeout(3000)
    await page.wait_for_load_state("networkidle")

    card_ids = []
    items = await page.locator("a.cardStr[data-src]").all()
    for item in items:
        data_src = await item.get_attribute("data-src")
        if data_src and "detailSearch=" in data_src:
            card_id = data_src.split("detailSearch=")[-1]
            if card_id not in card_ids:
                card_ids.append(card_id)

    print(f"  Found {len(card_ids)} cards for {set_code}")
    return card_ids

async def scrape_card_detail(page, card_id):
    url = DETAIL_BASE + card_id
    await page.goto(url, wait_until="networkidle")

    async def get_text(selector):
        try:
            el = page.locator(selector).first
            if await el.count():
                return (await el.inner_text()).strip()
        except:
            pass
        return ""

    # Correct selectors based on actual page HTML
    name = await get_text("h1.cardName")

    # Card code and rarity are in .cardNum and .rarity elements
    card_code = await get_text(".cardNo")
    rarity_raw = await get_text(".rarity")
    rarity, alt_art = parse_alt_art(rarity_raw)

    # Parse all dt/dd pairs into a dict
    details = {}
    rows = await page.locator("dl.dataBox").all()
    for row in rows:
        dt = row.locator("dt.dataTit")
        dd = row.locator("dd.dataTxt")
        if await dt.count() and await dd.count():
            label = (await dt.first.inner_text()).strip().lower()
            value = (await dd.first.inner_text()).strip()
            details[label] = value

    card_type    = details.get("type", "")
    color        = details.get("color", "")
    level        = parse_int(details.get("lv.") or details.get("lv"))
    cost         = parse_int(details.get("cost"))
    ap           = parse_int(details.get("ap"))
    hp           = parse_int(details.get("hp"))
    source_title = details.get("source title", "")

    # Effect text has its own container
    effect_text = await get_text(".dataTxt.isRegular")

    zones_raw = details.get("zone", "")
    zones = [z.strip() for z in zones_raw.split() if z.strip() and z.strip() != "-"]

    traits_raw = details.get("trait", "")
    traits = re.findall(r'\(([^)]+)\)', traits_raw) if traits_raw and traits_raw != "-" else []

    link_raw = details.get("link", "")
    links = re.findall(r'\[([^\]]+)\]', link_raw) if link_raw and link_raw != "-" else []

    image_url = ""
    img_el = page.locator(".cardImage img").first
    if await img_el.count():
        image_url = await img_el.get_attribute("src") or ""

    # Bandai's CDN blocks cross-origin image loads (Cross-Origin-Resource-Policy:
    # same-site), so LinkPear can't load image_url directly. Download it now
    # (with the Referer Bandai's CDN requires) and re-host it in our own
    # Supabase Storage bucket. image_url itself is left as Bandai's own path —
    # it's still the only reliable source for the true site listing-page id.
    hosted_image_url = download_and_host_image(image_url, card_code)

    return {
        "card_code":         card_code,
        "rarity":            rarity,
        "alt_art":           alt_art,
        "name":              name,
        "card_type":         card_type,
        "color":             color,
        "level":             level,
        "cost":              cost,
        "ap":                ap,
        "hp":                hp,
        "effect_text":       effect_text,
        "source_title":      source_title,
        "image_url":         image_url,
        "hosted_image_url":  hosted_image_url,
        "zones":             zones,
        "traits":            traits,
        "links":             links,
    }

async def run(set_codes=None):
    conn = get_connection()
    target_sets = [s for s in SETS if set_codes is None or s["set_code"] in set_codes]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for set_data in target_sets:
            print(f"\nProcessing {set_data['set_code']} — {set_data['name']}")
            set_id = upsert_set(conn, set_data)
            conn.commit()

            card_ids = await get_card_ids_for_set(page, set_data["set_code"], set_data.get("data_val"))

            for i, card_id in enumerate(card_ids):
                print(f"  [{i+1}/{len(card_ids)}] {card_id}")
                try:
                    card = await scrape_card_detail(page, card_id)
                    card["set_id"] = set_id
                    card_id_db = upsert_card(conn, card)
                    insert_zones(conn, card_id_db, card["zones"])
                    insert_traits(conn, card_id_db, card["traits"])
                    insert_link_conditions(conn, card_id_db, card["links"])
                    conn.commit()
                    print(f"    Saved: {card['card_code']} {card['rarity']}{card['alt_art']} — {card['name']}")
                except Exception as e:
                    print(f"    ERROR on {card_id}: {e}")
                    conn.rollback()

        await browser.close()
    conn.close()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(run())
