"""
backfill_images.py — one-off script for the image-hosting fix.

All 1,342 cards already in the DB were scraped before hosted_image_url
existed, so they all have hosted_image_url = NULL. The normal sync.py run
only scrapes *new* cards going forward, so it will never touch these
existing rows. Run this once to backfill every existing card, then
re-export cards.json so LinkPear picks up the hosted URLs.

Usage:
    python backfill_images.py

Safe to re-run: only cards where hosted_image_url IS NULL are processed,
and image_host.py uploads use x-upsert, so re-running after a partial
failure just picks up where it left off.
"""

import subprocess
import sys
import os

from db import get_connection
from image_host import download_and_host_image


def backfill():
    conn = get_connection()
    updated = 0
    failed = 0

    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, card_code, image_url
            FROM cards
            WHERE hosted_image_url IS NULL
            ORDER BY card_code
        """)
        rows = cur.fetchall()

    print(f"{len(rows)} card(s) missing a hosted image.")

    for i, (card_id, card_code, image_url) in enumerate(rows):
        print(f"[{i + 1}/{len(rows)}] {card_code}")
        hosted_url = download_and_host_image(image_url, card_code)
        if not hosted_url:
            print(f"    FAILED to host image for {card_code} (image_url={image_url!r})")
            failed += 1
            continue

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cards SET hosted_image_url = %s WHERE id = %s",
                (hosted_url, card_id),
            )
        conn.commit()
        updated += 1

    conn.close()

    print(f"\nBackfilled {updated} card(s), {failed} failure(s).")

    if updated > 0:
        print("Regenerating cards.json...")
        export_script = os.path.join(os.path.dirname(__file__), "export-cards.py")
        subprocess.run([sys.executable, export_script], check=True)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    backfill()
