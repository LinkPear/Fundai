"""
image_host.py — download Bandai card images and re-host them in our own
Supabase Storage bucket, so LinkPear (or any other consumer) can load them
cross-origin without hitting Bandai's `Cross-Origin-Resource-Policy: same-site`
header (ERR_BLOCKED_BY_RESPONSE.NotSameSite).

Bandai's CDN also appears to gate on Referer, so every download request
includes one.

Requires two env vars (see .env.example):
    SUPABASE_URL                 e.g. https://xxxx.supabase.co
    SUPABASE_SERVICE_ROLE_KEY    service_role secret — server-side only,
                                  never ship this to a client. Needed because
                                  the bucket has no anon-write policy; the
                                  service role bypasses RLS for the upload.

Uses the Storage REST API directly via `requests` rather than pulling in the
full supabase-py SDK, to match this codebase's existing minimal-dependency
style (raw psycopg2, no ORM).
"""

import os
import re
import requests

BANDAI_REFERER = "https://www.gundam-gcg.com/"
BUCKET = "card-images"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _filename_from_image_url(image_url, fallback_code):
    """
    Mirror export-cards.py's derive_code() / sync.py's site_id_for(): pull the
    real filename stem (e.g. "GD01-001_p1") straight out of Bandai's own path
    so our hosted copy uses the exact same name. That keeps id-derivation
    logic (which reads the *original* image_url column, untouched by this
    module) and the hosted filename in permanent agreement.
    """
    match = re.search(r'/([^/]+)\.webp', image_url or '')
    if match:
        return match.group(1).split('?')[0]
    return fallback_code


def download_and_host_image(image_url_relative, card_code):
    """
    image_url_relative: the raw value scraped from the page, e.g.
        "../images/cards/card/GD01-001_p1.webp?260612"
    card_code: fallback filename stem if the URL can't be parsed.

    Returns the public hosted URL on success, or None if anything failed
    (missing image, download error, upload error) — callers should treat
    None as "no hosted image yet" and leave the DB column untouched rather
    than overwrite a previously-good URL with a null.
    """
    if not image_url_relative:
        return None

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("    WARNING: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping image hosting")
        return None

    bandai_url = image_url_relative.replace('../', 'https://www.gundam-gcg.com/en/')
    filename = _filename_from_image_url(image_url_relative, card_code)
    storage_path = f"{filename}.webp"

    try:
        resp = requests.get(
            bandai_url,
            headers={"Referer": BANDAI_REFERER},
            timeout=30,
        )
        resp.raise_for_status()
        image_bytes = resp.content
    except requests.RequestException as e:
        print(f"    WARNING: failed to download {bandai_url}: {e}")
        return None

    upload_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
    try:
        put_resp = requests.post(
            upload_url,
            headers={
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "image/webp",
                "x-upsert": "true",  # idempotent: overwrite if this card was re-scraped
            },
            data=image_bytes,
            timeout=30,
        )
        put_resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: failed to upload {storage_path} to Supabase Storage: {e}")
        return None

    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"
