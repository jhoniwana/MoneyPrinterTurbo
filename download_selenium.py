import os
import time
import httpx
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://chat.qwen.ai/s/deploy/t_7aefc925-39af-4c9a-8350-02d61eb1c8b4"
OUTPUT_DIR = "/home/jhon/money/MoneyPrinterTurbo/storage/qwen_images"

os.makedirs(OUTPUT_DIR, exist_ok=True)

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

print("Starting Chrome...")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    print("Navigating...")
    driver.get(URL)
    time.sleep(10)

    for i in range(20):
        driver.execute_script("window.scrollBy(0, 300)")
        time.sleep(1.5)

    driver.execute_script("window.scrollTo(0, 0)")
    time.sleep(2)
    for i in range(25):
        driver.execute_script("window.scrollBy(0, 300)")
        time.sleep(1)

    driver.save_screenshot(os.path.join(OUTPUT_DIR, "selenium_screenshot.png"))
    print("Screenshot saved")

    html = driver.page_source
    with open(os.path.join(OUTPUT_DIR, "selenium_page.html"), "w") as f:
        f.write(html)
    print(f"HTML saved ({len(html)} chars)")

    imgs = driver.find_elements("tag name", "img")
    print(f"\nFound {len(imgs)} img elements:")
    image_urls = set()
    for img in imgs:
        src = img.get_attribute("src") or ""
        data_src = img.get_attribute("data-src") or ""
        for url in [src, data_src]:
            if url and url.startswith("http"):
                image_urls.add(url)
                print(f"  {url[:150]}")

    bg_imgs = driver.execute_script("""
        const urls = [];
        document.querySelectorAll('div, span, a, button, li').forEach(el => {
            const bg = getComputedStyle(el).backgroundImage;
            if (bg && bg !== 'none' && bg.includes('url(')) {
                const match = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
                if (match && match[1].startsWith('http')) urls.push(match[1]);
            }
        });
        return urls;
    """)
    print(f"\nBackground images: {len(bg_imgs)}")
    for url in bg_imgs:
        image_urls.add(url)
        print(f"  {url[:150]}")

    print(f"\nTotal unique URLs: {len(image_urls)}")

    downloaded = 0
    async def download_all():
        counter = 0
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for url in sorted(image_urls):
                if counter >= 20:
                    break
                try:
                    resp = await client.get(url)
                    ct = resp.headers.get("content-type", "")
                    if resp.status_code == 200 and len(resp.content) > 5000 and "svg" not in ct:
                        ext = ".jpg"
                        if "png" in ct: ext = ".png"
                        elif "webp" in ct: ext = ".webp"
                        elif "gif" in ct: ext = ".gif"
                        filename = f"sel_{counter+1:02d}{ext}"
                        filepath = os.path.join(OUTPUT_DIR, filename)
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                        counter += 1
                        print(f"Saved {filename} ({len(resp.content)} bytes)")
                except Exception as e:
                    print(f"Error: {e}")
        return counter

    downloaded = asyncio.run(download_all())
    print(f"\nTotal downloaded: {downloaded}")

finally:
    driver.quit()
    print("Browser closed")
