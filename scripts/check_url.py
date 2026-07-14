"""Manually inspect media URLs exposed by a shared Douyin page."""

import argparse
import asyncio
import json
import platform

from playwright.async_api import async_playwright


def _launch_args() -> dict:
    if platform.system() == "Windows":
        return {"channel": "msedge"}
    return {"executable_path": "/snap/bin/chromium", "args": ["--no-sandbox"]}


async def extract(share_url: str) -> list[str]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, **_launch_args())
        page = await browser.new_page()
        await page.goto(share_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        urls = await page.evaluate(
            """() => {
                const urls = [];
                document.querySelectorAll('video source, video').forEach(el => {
                    const src = el.src || el.getAttribute('src') || '';
                    if (src && (src.includes('douyinvod') || src.includes('zjcdn') || src.includes('aweme/v1/play')))
                        urls.push(src.substring(0, 120));
                });
                return urls;
            }"""
        )

        await browser.close()
        return urls


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("share_url", help="Public Douyin share URL to inspect")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(extract(args.share_url)), ensure_ascii=False))


if __name__ == "__main__":
    main()
