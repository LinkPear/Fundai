import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

def upsert_set(conn, set_data):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sets (set_code, name, product_type, release_date, scraped_at)
            VALUES (%(set_code)s, %(name)s, %(product_type)s, %(release_date)s, NOW())
            ON CONFLICT (set_code) DO UPDATE SET
                name = EXCLUDED.name,
                product_type = EXCLUDED.product_type,
                release_date = EXCLUDED.release_date,
                scraped_at = NOW()
            RETURNING id
        """, set_data)
        return cur.fetchone()[0]

def upsert_card(conn, card_data):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO cards (
                set_id, card_code, name, card_type, color,
                level, cost, ap, hp, effect_text,
                source_title, where_to_get, image_url, hosted_image_url, rarity, alt_art, scraped_at
            ) VALUES (
                %(set_id)s, %(card_code)s, %(name)s, %(card_type)s, %(color)s,
                %(level)s, %(cost)s, %(ap)s, %(hp)s, %(effect_text)s,
                %(source_title)s, %(where_to_get)s, %(image_url)s, %(hosted_image_url)s, %(rarity)s, %(alt_art)s, NOW()
            )
            ON CONFLICT (set_id, card_code, rarity, alt_art, where_to_get) DO UPDATE SET
                name = EXCLUDED.name,
                card_type = EXCLUDED.card_type,
                color = EXCLUDED.color,
                level = EXCLUDED.level,
                cost = EXCLUDED.cost,
                ap = EXCLUDED.ap,
                hp = EXCLUDED.hp,
                effect_text = EXCLUDED.effect_text,
                source_title = EXCLUDED.source_title,
                where_to_get = EXCLUDED.where_to_get,
                image_url = EXCLUDED.image_url,
                -- Never let a failed download (hosted_image_url = NULL) wipe out
                -- a previously-hosted image on re-scrape.
                hosted_image_url = COALESCE(EXCLUDED.hosted_image_url, cards.hosted_image_url),
                scraped_at = NOW()
            RETURNING id
        """, card_data)
        return cur.fetchone()[0]

def insert_traits(conn, card_id, traits):
    if not traits:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM traits WHERE card_id = %s", (card_id,))
        for trait in traits:
            cur.execute(
                "INSERT INTO traits (card_id, trait) VALUES (%s, %s)",
                (card_id, trait)
            )

def insert_zones(conn, card_id, zones):
    if not zones:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM zones WHERE card_id = %s", (card_id,))
        for zone in zones:
            cur.execute(
                "INSERT INTO zones (card_id, zone) VALUES (%s, %s)",
                (card_id, zone)
            )

def insert_link_conditions(conn, card_id, pilots):
    if not pilots:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM link_conditions WHERE card_id = %s", (card_id,))
        for pilot in pilots:
            cur.execute(
                "INSERT INTO link_conditions (card_id, pilot_name) VALUES (%s, %s)",
                (card_id, pilot)
            )
