"""
One-off diagnostic: dump every entry in the "Included In" (package) filter
dropdown on the main cards page, with both its data-val and visible text.

Why: sync.py's get_live_set_filters() only keeps entries whose data-val
matches SET_CODE_PATTERN (^[A-Z]{2,3}\\d{2}$ — e.g. GD01, ST01, EB01). New
site entries like "Deck Build Box Freedom Ascension", "Edition Beta",
"Promotion card", "Basic Cards", and "Other Product Card" are being
silently dropped by that filter and never reach new-set detection. Before
fixing the pattern/matching logic we need to see their real data-val
values and confirm whether a[data-val] on this page picks up anything
outside the package dropdown (rarity/type/trait/etc. use checkboxes, not
this pattern, but confirming beats assuming).

Run with: python debug_package_filters.py
Prints a data-val | text table and saves package_filters.png for a visual
double-check.
"""
import asyncio
from playwright.async_api import async_playwright

BASE_URL = "https://www.gundam-gcg.com/en/cards/"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(BASE_URL, wait_until="networkidle")

        try:
            accept = page.locator("#onetrust-accept-btn-handler")
            if await accept.count() > 0:
                await accept.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass

        # Open the "Included In" dropdown so its full option list is in the DOM
        # (mirrors the site's own accordion toggle, not a specific set click).
        try:
            toggle = page.locator(".js-selectBtn-package").first
            if await toggle.count() > 0:
                await toggle.evaluate("el => el.click()")
                await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"Couldn't click dropdown toggle (may already be open): {e}")

        links = await page.locator("a[data-val]").all()
        print(f"Found {len(links)} a[data-val] elements on the page total:\n")
        print(f"{'data-val':30} | text")
        print("-" * 70)
        for link in links:
            val = await link.get_attribute("data-val")
            text = (await link.inner_text()).strip()
            print(f"{(val or ''):30} | {text}")

        await page.screenshot(path="package_filters.png", full_page=True)
        print("\nScreenshot saved: package_filters.png")

        await browser.close()

asyncio.run(run())
