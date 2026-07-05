import json
import os
import re
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

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
    e.g. GD01-001        (base)
         GD01-001_p1     (+)
         GD01-001_p2     (++)
         GD01-001_SP     (SP)
    """
    if not alt_art:
        return card_code

    # Extract filename stem from image URL
    # e.g. "../images/cards/card/GD01-001_p1.webp?260612" -> "GD01-001_p1"
    match = re.search(r'/([^/]+)\.webp', image_url or '')
    if match:
        stem = match.group(1).split('?')[0]
        return stem

    # Fallback if image URL is missing
    if alt_art == '+':
        return f"{card_code}_p1"
    elif alt_art == '++':
        return f"{card_code}_p2"
    elif alt_art == 'SP':
        return f"{card_code}_SP"
    return card_code

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
                c.image_url,
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
        image = derive_image_url(row['image_url'])

        # Combine rarity + alt_art to match APITCGcom convention e.g. "LR", "LR+", "LR++"
        rarity = row['rarity'] or ''
        alt_art = row['alt_art'] or ''
        rarity_display = f"{rarity}{alt_art}".strip()

        # Join child arrays back to strings (matching current Prisma schema)
        zones = zones_by_card.get(card_id, [])
        traits = traits_by_card.get(card_id, [])
        links = links_by_card.get(card_id, [])

        cards.append({
            "id": code,                                    # use derived code as stable ID
            "code": code,
            "cardCode": row['card_code'],                  # original e.g. GD01-001
            "altArt": alt_art,                             # "", "+", "++", "SP"
            "name": row['name'],
            "rarity": rarity_display,                      # e.g. "LR", "LR+", "C"
            "color": row['color'],
            "cardType": row['card_type'],
            "level": str(row['level']) if row['level'] is not None else None,
            "cost": str(row['cost']) if row['cost'] is not None else None,
            "ap": str(row['ap']) if row['ap'] is not None else None,
            "hp": str(row['hp']) if row['hp'] is not None else None,
            "effect": row['effect_text'],
            "zone": ' '.join(zones) if zones else None,
            "trait": ', '.join(f"({t})" for t in traits) if traits else None,
            "link": ' '.join(f"[{l}]" for l in links) if links else None,
            "sourceTitle": row['source_title'],
            "imageSmall": image,
            "imageLarge": image,
            "setName": row['set_name'],
            "setCode": row['set_code'],
            "game": "gundam",
        })

    output_path = os.path.join(os.path.dirname(__file__), 'cards.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(cards)} cards to {output_path}")

if __name__ == "__main__":
    export()
