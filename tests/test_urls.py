import asyncio, json, platform, sys
from playwright.async_api import async_playwright

SHARE_URL = sys.argv[1]

def _launch_args():
    if platform.system() == "Windows":
        return {"channel": "msedge"}
    return {"executable_path": "/snap/bin/chromium", "args": ["--no-sandbox"]}

async def extract():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, **_launch_args())
        page = await browser.new_page()
        await page.goto(SHARE_URL, wait_until='domcontentloaded', timeout=15000)
        await page.wait_for_timeout(3000)

        urls = await page.evaluate("""() => {
            const urls = [];
            document.querySelectorAll('video source, video').forEach(el => {
                const src = el.src || el.getAttribute('src') || '';
                if (src && (src.includes('douyinvod') || src.includes('zjcdn') || src.includes('aweme/v1/play')))
                    urls.push(src.substring(0, 120));
            });
            return urls;
        }""")

        await browser.close()
        return urls

result = asyncio.run(extract())
print(json.dumps(result))
