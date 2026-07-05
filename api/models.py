from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
import uuid


class SetOut(BaseModel):
    id: uuid.UUID
    set_code: str
    name: str
    product_type: str
    release_date: Optional[date]
    scraped_at: Optional[datetime]

    class Config:
        from_attributes = True


class CardSummary(BaseModel):
    id: uuid.UUID
    set_id: uuid.UUID
    card_code: str
    name: str
    card_type: str
    color: str
    level: Optional[int]
    cost: Optional[int]
    ap: Optional[int]
    hp: Optional[int]
    rarity: str
    alt_art: str
    image_url: Optional[str]
    source_title: Optional[str]

    class Config:
        from_attributes = True


class CardDetail(CardSummary):
    effect_text: Optional[str]
    scraped_at: Optional[datetime]
    zones: list[str] = []
    traits: list[str] = []
    link_conditions: list[str] = []
