#!/usr/bin/env python3
"""
token_pairs.py — Link each card to the Unit Token(s) it produces.

Token creation in Gundam card text follows a consistent structure, e.g.:

    Deploy 1 rested [Char's Zaku II]((Zeon)·AP3·HP1) Unit token.
    Deploy 1 [Fatum-00]((Triple Ship Alliance)·AP2·HP2·<Blocker>) Unit token.

The reliable anchor is the phrase "Unit token", with the token NAME in [square
brackets] immediately before it and the stats in a (trait·APx·HPy·...) block.
We do NOT anchor on the [Deploy] keyword — that is the generic on-enter trigger
and appears on ~350 cards. Cards that merely reference an existing token
("all your Unit tokens get AP+1") have no bracketed name and are ignored.

Each parsed reference is resolved to a real UNIT TOKEN card record by
name (+ AP / HP to disambiguate any future name collisions).

Public API (used by export-cards.py):
    compute_pairs(cards)   -> (pairs, unresolved)
    producers_map(pairs)   -> {producer_code: [{"code","name","count"}, ...]}

CLI (standalone review):
    python token_pairs.py                 # print the pairing report
    python token_pairs.py --json out.json # also write structured pairs to JSON
"""

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

CARDS_JSON = os.path.join(os.path.dirname(__file__), "cards.json")

TOKEN_TYPES = {"UNIT TOKEN"}  # normalized (fullwidth "・" -> space)

# "[Name] ...stats... Unit token"
#  - group 1: bracketed token name
#  - group 2: everything up to the literal "Unit token" (holds the stat block).
# The stats sit in a single-paren block whose first element is a parenthesized
# trait, e.g. [Fatum-00]((Triple Ship Alliance)·AP2·HP2·<Blocker>), so we don't
# try to balance parens — we grab the span and mine AP/HP from it. [^.\n] keeps
# the match inside one sentence so we can't run past the creation clause.
TOKEN_RE = re.compile(
    r"\[([^\]]+)\]"          # [Name]
    r"([^.\n]*?)"            # stat block + any small gap (no sentence break)
    r"Unit\s*token",          # anchor
    re.IGNORECASE,
)

AP_RE = re.compile(r"AP\s*(\d+)", re.IGNORECASE)
HP_RE = re.compile(r"HP\s*(\d+)", re.IGNORECASE)


def norm_type(t: str) -> str:
    return (t or "").replace("・", " ").strip().upper()


def norm_name(s: str) -> str:
    # NFKC folds fullwidth roman numerals (Ⅱ) etc.; then lower + collapse space
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _to_int(v):
    """AP/HP may arrive as int (DB rows) or str (cards.json export) or None."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def build_token_index(cards):
    """normalized name -> [token records], deduped by cardCode."""
    by_code = {}
    for c in cards:
        if norm_type(c.get("cardType", "")) in TOKEN_TYPES:
            by_code.setdefault(c["cardCode"], c)
    by_name = defaultdict(list)
    for c in by_code.values():
        by_name[norm_name(c["name"])].append(c)
    return by_name


def resolve(name, stats_block, by_name):
    """Return (token_record, reason) or (None, reason)."""
    cands = by_name.get(norm_name(name), [])
    if not cands:
        return None, "no token record with that name"
    if len(cands) == 1:
        return cands[0], "name (unique)"
    # disambiguate on AP / HP pulled from the stat block
    ap = AP_RE.search(stats_block)
    hp = HP_RE.search(stats_block)
    ap = int(ap.group(1)) if ap else None
    hp = int(hp.group(1)) if hp else None
    narrowed = [c for c in cands
                if (ap is None or _to_int(c.get("ap")) == ap)
                and (hp is None or _to_int(c.get("hp")) == hp)]
    if len(narrowed) == 1:
        return narrowed[0], "name + AP/HP"
    return None, f"ambiguous ({len(cands)} same-name tokens, AP/HP didn't isolate)"


def compute_pairs(cards):
    """Scan every card's effect for token-creation clauses.

    Returns (pairs, unresolved):
      pairs      -> list of {producer_code, producer_name,
                             token_code, token_name, count}
      unresolved -> list of {producer_code, producer_name, wanted_name,
                             stats, reason}   (should stay empty)
    Producing cards are deduped by cardCode (the export has one row per art
    variant, all sharing the same effect text).
    """
    by_name = build_token_index(cards)
    seen_codes = set()
    pairs, unresolved = [], []

    for c in cards:
        code = c["cardCode"]
        if code in seen_codes:
            continue
        eff = c.get("effect") or ""
        matches = list(TOKEN_RE.finditer(eff))
        if not matches:
            continue
        seen_codes.add(code)
        for m in matches:
            raw_name, stats = m.group(1), m.group(2)
            # count = the "Deploy N [" number just before the bracket, if any
            pre = eff[max(0, m.start() - 24):m.start()]
            cnt = re.search(r"(\d+)\D*$", pre)
            count = int(cnt.group(1)) if cnt else 1
            tok, reason = resolve(raw_name, stats, by_name)
            if tok:
                pairs.append({
                    "producer_code": code,
                    "producer_name": c["name"],
                    "token_code": tok["cardCode"],
                    "token_name": tok["name"],
                    "count": count,
                })
            else:
                unresolved.append({
                    "producer_code": code,
                    "producer_name": c["name"],
                    "wanted_name": raw_name,
                    "stats": stats,
                    "reason": reason,
                })
    return pairs, unresolved


def producers_map(pairs):
    """{producer_code: [{"code","name","count"}, ...]} for inline embedding."""
    m = defaultdict(list)
    for p in pairs:
        m[p["producer_code"]].append({
            "code": p["token_code"],
            "name": p["token_name"],
            "count": p["count"],
        })
    return m


def main():
    with open(CARDS_JSON) as f:
        cards = json.load(f)
    pairs, unresolved = compute_pairs(cards)
    producers = {p["producer_code"] for p in pairs}

    print(f"Producing cards found: {len(producers)}")
    print(f"Resolved token references: {len(pairs)}")
    print(f"Unresolved references: {len(unresolved)}\n")

    print("=== PRODUCING CARD  ->  TOKEN ===")
    for p in sorted(pairs, key=lambda x: x["producer_code"]):
        print(f"{p['producer_code']:<10} {p['producer_name']:<32} -> "
              f"{p['count']}x {p['token_code']:<7} {p['token_name']}")

    if unresolved:
        print("\n=== UNRESOLVED (needs a look) ===")
        for u in unresolved:
            print(f"{u['producer_code']:<10} {u['producer_name']:<28} "
                  f"wants [{u['wanted_name']}]  -- {u['reason']}")

    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(pairs, f, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(pairs)} pairs -> {out}")


if __name__ == "__main__":
    main()
