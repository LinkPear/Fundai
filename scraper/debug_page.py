import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.gundam-gcg.com/en/cards/", wait_until="networkidle")
        await page.screenshot(path="page_loaded.png", full_page=True)
        print("Screenshot saved as page_loaded.png")

        content = await page.content()
        with open("page_source.html", "w") as f:
            f.write(content)
        print("Page source saved as page_source.html")

        await browser.close()

asyncio.run(run())
