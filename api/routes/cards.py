from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from api.db import get_connection
from api.models import CardSummary, CardDetail
import uuid

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=list[CardSummary])
def list_cards(
    color:   Optional[str] = Query(None),
    type:    Optional[str] = Query(None),
    rarity:  Optional[str] = Query(None),
    alt_art: Optional[str] = Query(None),
    level:   Optional[int] = Query(None),
    cost:    Optional[int] = Query(None),
    zone:    Optional[str] = Query(None),
    trait:   Optional[str] = Query(None),
    link:    Optional[str] = Query(None),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            conditions = []
            params = []

            if color:
                conditions.append("c.color ILIKE %s")
                params.append(color)
            if type:
                conditions.append("c.card_type ILIKE %s")
                params.append(type)
            if rarity:
                conditions.append("c.rarity ILIKE %s")
                params.append(rarity)
            if alt_art is not None:
                conditions.append("c.alt_art = %s")
                params.append(alt_art)
            if level is not None:
                conditions.append("c.level = %s")
                params.append(level)
            if cost is not None:
                conditions.append("c.cost = %s")
                params.append(cost)
            if zone:
                conditions.append("""
                    EXISTS (
                        SELECT 1 FROM zones z
                        WHERE z.card_id = c.id AND z.zone ILIKE %s
                    )
                """)
                params.append(zone)
            if trait:
                conditions.append("""
                    EXISTS (
                        SELECT 1 FROM traits t
                        WHERE t.card_id = c.id AND t.trait ILIKE %s
                    )
                """)
                params.append(trait)
            if link:
                conditions.append("""
                    EXISTS (
                        SELECT 1 FROM link_conditions lc
                        WHERE lc.card_id = c.id AND lc.pilot_name ILIKE %s
                    )
                """)
                params.append(link)

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            cur.execute(f"""
                SELECT c.id, c.set_id, c.card_code, c.name, c.card_type, c.color,
                       c.level, c.cost, c.ap, c.hp, c.rarity, c.alt_art,
                       c.image_url, c.source_title
                FROM cards c
                {where}
                ORDER BY c.card_code, c.alt_art
            """, params)
            return cur.fetchall()
    finally:
        conn.close()


@router.get("/{card_id}", response_model=CardDetail)
def get_card(card_id: uuid.UUID):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.set_id, c.card_code, c.name, c.card_type, c.color,
                       c.level, c.cost, c.ap, c.hp, c.rarity, c.alt_art,
                       c.image_url, c.source_title, c.effect_text, c.scraped_at
                FROM cards c
                WHERE c.id = %s
            """, (str(card_id),))
            card = cur.fetchone()
            if not card:
                raise HTTPException(status_code=404, detail="Card not found")

            card = dict(card)

            cur.execute("SELECT zone FROM zones WHERE card_id = %s", (str(card_id),))
            card["zones"] = [r["zone"] for r in cur.fetchall()]

            cur.execute("SELECT trait FROM traits WHERE card_id = %s", (str(card_id),))
            card["traits"] = [r["trait"] for r in cur.fetchall()]

            cur.execute("SELECT pilot_name FROM link_conditions WHERE card_id = %s", (str(card_id),))
            card["link_conditions"] = [r["pilot_name"] for r in cur.fetchall()]

            return card
    finally:
        conn.close()
