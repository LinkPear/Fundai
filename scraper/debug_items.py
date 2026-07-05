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

        set_link = page.locator("a[data-val]").filter(has_text="GD01")
        await set_link.first.evaluate("el => el.click()")
        await page.wait_for_timeout(3000)
        await page.wait_for_load_state("networkidle")

        # Dump a large chunk of the page HTML around the card results
        html = await page.content()

        # Find the card list section
        start = html.find("179cards found")
        if start == -1:
            start = html.find("cards found")
        
        print("HTML around card results:")
        print(html[start:start+3000])

        await browser.close()

asyncio.run(run())
