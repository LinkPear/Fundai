import asyncio
from playwright.async_api import async_playwright

BASE_URL = "https://www.gundam-gcg.com/en/cards/"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(BASE_URL, wait_until="networkidle")

        # Dismiss cookie banner
        try:
            accept = page.locator("#onetrust-accept-btn-handler")
            if await accept.count() > 0:
                await accept.click()
                await page.wait_for_timeout(500)
        except:
            pass

        # Click GD01 filter
        set_link = page.locator("a[data-val]").filter(has_text="GD01")
        print(f"Found {await set_link.count()} matching filter links")
        await set_link.first.evaluate("el => el.click()")
        await page.wait_for_timeout(3000)
        await page.wait_for_load_state("networkidle")

        # Take a screenshot to see what happened
        await page.screenshot(path="after_filter.png", full_page=True)
        print("Screenshot saved: after_filter.png")

        # Print ALL links on the page after filtering
        all_links = await page.locator("a[href]").all()
        print(f"\nAll links found after filter click ({len(all_links)} total):")
        for a in all_links[:40]:
            href = await a.get_attribute("href")
            text = (await a.inner_text()).strip()[:50]
            print(f"  {href} | {text}")

        await browser.close()

asyncio.run(run())
