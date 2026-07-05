from fastapi import APIRouter, HTTPException
from api.db import get_connection
from api.models import SetOut, CardSummary

router = APIRouter(prefix="/sets", tags=["sets"])


@router.get("", response_model=list[SetOut])
def list_sets():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM sets ORDER BY set_code")
            return cur.fetchall()
    finally:
        conn.close()


@router.get("/{set_code}/cards", response_model=list[CardSummary])
def cards_by_set(set_code: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM sets WHERE set_code = %s", (set_code.upper(),))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Set '{set_code}' not found")

            cur.execute("""
                SELECT c.id, c.set_id, c.card_code, c.name, c.card_type, c.color,
                       c.level, c.cost, c.ap, c.hp, c.rarity, c.alt_art,
                       c.image_url, c.source_title
                FROM cards c
                WHERE c.set_id = %s
                ORDER BY c.card_code, c.alt_art
            """, (row["id"],))
            return cur.fetchall()
    finally:
        conn.close()
