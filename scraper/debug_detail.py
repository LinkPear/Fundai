import asyncio
from playwright.async_api import async_playwright

URL = "https://www.gundam-gcg.com/en/cards/detail.php?detailSearch=GD01-059"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle")

        html = await page.content()

        idx = html.find("Zee Zulu")
        if idx == -1:
            idx = html.find("GD01-059")
        if idx == -1:
            print("Card content not found in HTML")
            print("Page title:", await page.title())
            print("\nFirst 2000 chars:")
            print(html[:2000])
        else:
            print(f"Found card content at position {idx}")
            print(html[max(0, idx-200):idx+3000])

        await browser.close()

asyncio.run(run())
