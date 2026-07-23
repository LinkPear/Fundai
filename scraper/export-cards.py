import json
import os
import re
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from token_pairs import compute_pairs, producers_map

load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def derive_code(card_code, alt_art, image_url):
    """
    Derive a unique card code from the image URL filename,
    mirroring Bandai's own naming convention exactly.
    e.g. GD01-001        (base, first printing)
         GD01-001_p1     (+, or a later reprint of the base rarity)
         GD01-001_p2     (++, or a later reprint)
         GD01-001_SP     (SP)

    The "_pN" suffix is a running reprint counter, not tied to alt_art —
    a plain base-rarity (alt_art == "") reprint can still carry a "_pN"
    suffix once that card_code has been printed more than once. So the
    image_url lookup must run regardless of alt_art; only fall back to
    the symbolic alt_art mapping if image_url is missing entirely.
    """
    # Extract filename stem from image URL
    # e.g. "../images/cards/card/GD01-001_p1.webp?260612" -> "GD01-001_p1"
    match = re.search(r'/([^/]+)\.webp', image_url or '')
    if match:
        stem = match.group(1).split('?')[0]
        return stem

    if not alt_art:
        return card_code

    # Fallback if image URL is missing
    if alt_art == '+':
        return f"{card_code}_p1"
    elif alt_art == '++':
        return f"{card_code}_p2"
    elif alt_art == 'SP':
        return f"{card_code}_SP"
    return card_code

# Same normalization the scraper applies (scraper.normalize_card_type): fold
# fullwidth dot variants to a space so "UNIT・TOKEN" and "UNIT TOKEN" don't
# split into two types. Applied here too so cards.json is always canonical even
# for DB rows scraped before that fix landed (no re-scrape required).
_CARD_TYPE_DOTS = str.maketrans({"・": " ", "･": " ", "·": " "})


def normalize_card_type(value):
    return re.sub(r"\s+", " ", (value or "").translate(_CARD_TYPE_DOTS)).strip()


def derive_image_url(image_url):
    """
    Convert relative Bandai CDN path to absolute URL.
    e.g. "../images/cards/card/GD01-001.webp?260612"
      -> "https://www.gundam-gcg.com/en/images/cards/card/GD01-001.webp?260612"
    """
    if not image_url:
        return None
    return image_url.replace('../', 'https://www.gundam-gcg.com/en/')

def export():
    conn = get_connection()
    cards = []

    with conn.cursor() as cur:
        # Fetch all cards with their set name
        cur.execute("""
            SELECT 
                c.id,
                c.card_code,
                c.name,
                c.rarity,
                c.alt_art,
                c.color,
                c.card_type,
                c.level,
                c.cost,
                c.ap,
                c.hp,
                c.effect_text,
                c.source_title,
                c.where_to_get,
                c.image_url,
                c.hosted_image_url,
                s.name AS set_name,
                s.set_code
            FROM cards c
            JOIN sets s ON s.id = c.set_id
            ORDER BY s.set_code, c.card_code, c.alt_art
        """)
        rows = cur.fetchall()

        # Fetch child tables into lookup dicts
        cur.execute("SELECT card_id, zone FROM zones")
        zones_by_card = {}
        for r in cur.fetchall():
            zones_by_card.setdefault(r['card_id'], []).append(r['zone'])

        cur.execute("SELECT card_id, trait FROM traits")
        traits_by_card = {}
        for r in cur.fetchall():
            traits_by_card.setdefault(r['card_id'], []).append(r['trait'])

        cur.execute("SELECT card_id, pilot_name FROM link_conditions")
        links_by_card = {}
        for r in cur.fetchall():
            links_by_card.setdefault(r['card_id'], []).append(r['pilot_name'])

    for row in rows:
        card_id = row['id']
        code = derive_code(row['card_code'], row['alt_art'], row['image_url'])

        # imageSmall/imageLarge must point at our own hosted copy, never at
        # Bandai's CDN — Bandai sends Cross-Origin-Resource-Policy: same-site,
        # which blocks LinkPear (a different origin) from loading the image
        # at all (ERR_BLOCKED_BY_RESPONSE.NotSameSite). hosted_image_url is
        # populated at scrape time (see image_host.py); the Bandai URL is
        # kept only as a last-resort fallback for any row that predates this
        # fix and hasn't been backfilled yet (run backfill_images.py).
        image = row['hosted_image_url'] or derive_image_url(row['image_url'])

        # Combine rarity + alt_art to match APITCGcom convention e.g. "LR", "LR+", "LR++"
        rarity = row['rarity'] or ''
        alt_art = row['alt_art'] or ''
        rarity_display = f"{rarity}{alt_art}".strip()

        # Join child arrays back to strings (matching current Prisma schema)
        zones = zones_by_card.get(card_id, [])
        traits = traits_by_card.get(card_id, [])
        links = links_by_card.get(card_id, [])

        # Fold set code into the id: the same card_code/alt_art/rarity can
        # legitimately appear in multiple sets (reprints), so `code` alone
        # is not unique across the whole export — set_code makes it so.
        card_id = f"{row['set_code']}-{code}"

        cards.append({
            "id": card_id,                                 # set-qualified, stable, unique ID
            "code": code,
            "cardCode": row['card_code'],                  # original e.g. GD01-001
            "altArt": alt_art,                             # "", "+", "++", "SP"
            "name": row['name'],
            "rarity": rarity_display,                      # e.g. "LR", "LR+", "C"
            "color": row['color'],
            "cardType": normalize_card_type(row['card_type']),
            "level": str(row['level']) if row['level'] is not None else None,
            "cost": str(row['cost']) if row['cost'] is not None else None,
            "ap": str(row['ap']) if row['ap'] is not None else None,
            "hp": str(row['hp']) if row['hp'] is not None else None,
            "effect": row['effect_text'],
            "zone": ' '.join(zones) if zones else None,
            "trait": ', '.join(f"({t})" for t in traits) if traits else None,
            "link": ' '.join(f"[{l}]" for l in links) if links else None,
            "sourceTitle": row['source_title'],
            "whereToGet": row['where_to_get'],
            "imageSmall": image,
            "imageLarge": image,
            "setName": row['set_name'],
            "setCode": row['set_code'],
            "game": "gundam",
        })

    # --- Token pairing -------------------------------------------------
    # Derive which cards create Unit Tokens straight from the effect text we
    # just exported (see token_pairs.py). We attach the result inline to each
    # producing card as `producedTokens` so the app can read it without a join,
    # and also write a standalone token_pairs.json for review/debugging.
    # A producing card_code can have several art-variant rows; every one gets
    # the same list. cardType == "UNIT TOKEN" cards are the tokens themselves.
    pairs, unresolved = compute_pairs(cards)
    tokens_by_producer = producers_map(pairs)
    for card in cards:
        toks = tokens_by_producer.get(card['cardCode'])
        if toks:
            card['producedTokens'] = toks

    output_path = os.path.join(os.path.dirname(__file__), 'cards.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    pairs_path = os.path.join(os.path.dirname(__file__), 'token_pairs.json')
    with open(pairs_path, 'w', encoding='utf-8') as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)

    producer_count = len({p['producer_code'] for p in pairs})
    print(f"Exported {len(cards)} cards to {output_path}")
    print(f"Token pairing: {producer_count} producing cards, "
          f"{len(pairs)} token links -> {pairs_path}")
    if unresolved:
        print(f"  WARNING: {len(unresolved)} token reference(s) did not "
              f"resolve — check token_pairs.py / a name mismatch:")
        for u in unresolved:
            print(f"    {u['producer_code']} {u['producer_name']}: "
                  f"wants [{u['wanted_name']}] ({u['reason']})")

if __name__ == "__main__":
    export()
