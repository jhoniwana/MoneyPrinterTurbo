import asyncio
import os
import httpx
from playwright.async_api import async_playwright

URL = "https://chat.qwen.ai/s/deploy/t_7aefc925-39af-4c9a-8350-02d61eb1c8b4"
OUTPUT_DIR = "/home/jhon/money/MoneyPrinterTurbo/storage/qwen_images"

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # Capture ALL network requests
        async def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            if any(t in ct for t in ["image/", "video/"]):
                all_urls.add(url)
            elif any(ext in url.lower() for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]):
                all_urls.add(url)

        page.on("response", on_response)

        print("Navigating...")
        await page.goto(URL, wait_until="networkidle", timeout=90000)
        await asyncio.sleep(8)

        # Take screenshot to see what's there
        await page.screenshot(path=os.path.join(OUTPUT_DIR, "screenshot.png"), full_page=True)
        print("Screenshot saved")

        # Get page HTML to analyze
        html = await page.content()
        with open(os.path.join(OUTPUT_DIR, "page.html"), "w") as f:
            f.write(html)
        print(f"HTML saved ({len(html)} chars)")

        # Scroll multiple times
        for i in range(20):
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(1.5)
        await asyncio.sleep(3)

        # Get all img tags with more attributes
        imgs = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('img').forEach(img => {
                    results.push({
                        src: img.src,
                        srcset: img.srcset || '',
                        dataSrc: img.dataset.src || img.dataset.original || '',
                        alt: img.alt || '',
                        width: img.naturalWidth,
                        height: img.naturalHeight
                    });
                });
                return results;
            }
        """)
        print(f"\nFound {len(imgs)} img elements:")
        for img in imgs:
            print(f"  src={img['src'][:100]}... size={img['width']}x{img['height']}")
            if img['src'].startswith("http"):
                all_urls.add(img['src'])
            if img['dataSrc'] and img['dataSrc'].startswith("http"):
                all_urls.add(img['dataSrc'])

        # Check for any canvas elements (Qwen might render images on canvas)
        canvases = await page.evaluate("() => document.querySelectorAll('canvas').length")
        print(f"\nCanvas elements: {canvases}")

        # Check for iframes
        frames = page.frames
        print(f"Frames: {len(frames)}")
        for frame in frames:
            print(f"  Frame: {frame.url[:100]}")

        await browser.close()

    print(f"\nTotal unique image URLs captured: {len(all_urls)}")
    for u in sorted(all_urls):
        print(f"  {u[:150]}")

    # Download
    downloaded = 0
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for url in sorted(all_urls):
            if downloaded >= 20:
                break
            try:
                resp = await client.get(url)
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ("image" in ct or len(resp.content) > 5000):
                    ext = ".jpg"
                    if "png" in ct: ext = ".png"
                    elif "webp" in ct: ext = ".webp"
                    elif "gif" in ct: ext = ".gif"
                    elif "svg" in ct: continue
                    filename = f"img_{downloaded+1:02d}{ext}"
                    filepath = os.path.join(OUTPUT_DIR, filename)
                    with open(filepath, "wb") as f:
                        f.write(resp.content)
                    downloaded += 1
                    print(f"Saved {filename} ({len(resp.content)} bytes) from {url[:80]}")
            except Exception as e:
                print(f"Error: {e}")

    print(f"\nTotal downloaded: {downloaded}")

asyncio.run(main())
