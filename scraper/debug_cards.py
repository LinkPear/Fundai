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
        except:
            pass

        # Click GD01 filter
        set_link = page.locator("a[data-val]").filter(has_text="GD01")
        await set_link.first.evaluate("el => el.click()")
        await page.wait_for_timeout(3000)
        await page.wait_for_load_state("networkidle")

        # Dump the inner HTML of the card results area
        # Try common card list container selectors
        for selector in [".card-list", ".cards-list", ".card-item", ".js-card-item",
                         "[class*='card']", ".result", ".item-list", "ul.list", ".cardList"]:
            els = await page.locator(selector).all()
            if els:
                print(f"\nFound {len(els)} elements matching '{selector}'")
                # Print the outer HTML of the first one
                html = await els[0].evaluate("el => el.outerHTML")
                print(html[:500])
                break

        # Also print any elements with data-* attributes that look like card IDs
        print("\n--- Elements with data-id or data-card attributes ---")
        for selector in ["[data-id]", "[data-card]", "[data-code]", "[data-seq]"]:
            els = await page.locator(selector).all()
            if els:
                print(f"Found {len(els)} elements matching '{selector}'")
                for el in els[:3]:
                    html = await el.evaluate("el => el.outerHTML")
                    print(html[:300])

        # Print page body snippet around card results
        print("\n--- Page body snippet (card area) ---")
        body = await page.locator("body").inner_text()
        # Find where card names might appear
        lines = [l.strip() for l in body.split("\n") if l.strip()]
        for i, line in enumerate(lines[:100]):
            print(line)

        await browser.close()

asyncio.run(run())
