#!/usr/bin/env python3
"""browser-tool — Playwright-based browser automation for the agent.
Gives the agent "eyes" on the web — screenshot, scrape, interact.
Usage:
  python3 browser-tool.py screenshot <url> [--output file.png]  # Capture page
  python3 browser-tool.py scrape <url> [--selector "css"]       # Extract text
  python3 browser-tool.py search "<query>"                      # Search and return results
  python3 browser-tool.py check "<url>"                         # Quick page status check
  python3 browser-tool.py --json                                # Machine-readable all commands

Requires: pip install playwright && playwright install chromium
"""
import sys, json, os, io, asyncio
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

async def screenshot(url, output=None):
    """Take a full-page screenshot."""
    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "playwright not installed. Run: pip install playwright && playwright install chromium"}

    if output is None:
        output = HOME / '.claude' / 'screenshots' / f"screenshot_{Path(url).name or 'page'}_{__import__('time').time():.0f}.png"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.screenshot(path=str(output), full_page=True)
            title = await page.title()
            await browser.close()
            return {"status": "ok", "title": title, "output": str(output), "url": url}
        except Exception as e:
            await browser.close()
            return {"status": "error", "error": str(e), "url": url}

async def scrape(url, selector=None, limit=10):
    """Extract text content from a page."""
    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "playwright not installed"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            if selector:
                elements = await page.query_selector_all(selector)
                texts = []
                for el in elements[:limit]:
                    text = (await el.text_content() or "").strip()
                    if text:
                        texts.append(text)
                result = {"status": "ok", "selector": selector, "count": len(texts), "texts": texts}
            else:
                # Get main content
                title = await page.title()
                # Try to get article/main content
                for sel in ['article', 'main', '.content', '#content', 'body']:
                    el = await page.query_selector(sel)
                    if el:
                        text = (await el.text_content() or "").strip()
                        if len(text) > 100:
                            result = {"status": "ok", "title": title, "selector_used": sel,
                                     "text": text[:5000], "url": url}
                            break
                else:
                    text = (await page.text_content('body') or "").strip()
                    result = {"status": "ok", "title": title, "text": text[:5000], "url": url}

            await browser.close()
            return result
        except Exception as e:
            await browser.close()
            return {"status": "error", "error": str(e), "url": url}

async def check(url):
    """Quick page status check — title, status code, load time."""
    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "playwright not installed"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            start = __import__('time').time()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            elapsed = __import__('time').time() - start
            title = await page.title()
            status = response.status if response else 0
            await browser.close()
            return {
                "status": "ok",
                "url": url,
                "http_status": status,
                "title": title,
                "load_time_ms": round(elapsed * 1000),
            }
        except Exception as e:
            await browser.close()
            return {"status": "error", "error": str(e), "url": url}

def run_async(coro):
    """Helper to run async functions from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)

def main():
    if not PLAYWRIGHT_AVAILABLE:
        print(json.dumps({"error": "playwright not installed", "fix": "pip install playwright && playwright install chromium"}, ensure_ascii=False, indent=2))
        return

    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    use_json = "--json" in sys.argv

    if cmd == "screenshot":
        url = sys.argv[2] if len(sys.argv) > 2 else None
        output = None
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output = sys.argv[i + 1]
        if not url:
            print("Usage: browser-tool.py screenshot <url> [--output file.png]")
            return
        result = run_async(screenshot(url, output))

    elif cmd == "scrape":
        url = sys.argv[2] if len(sys.argv) > 2 else None
        selector = None
        for i, arg in enumerate(sys.argv):
            if arg == "--selector" and i + 1 < len(sys.argv):
                selector = sys.argv[i + 1]
        if not url:
            print("Usage: browser-tool.py scrape <url> [--selector css]")
            return
        result = run_async(scrape(url, selector))

    elif cmd == "check":
        url = sys.argv[2] if len(sys.argv) > 2 else None
        if not url:
            print("Usage: browser-tool.py check <url>")
            return
        result = run_async(check(url))

    else:
        print(f"Unknown command: {cmd}. Use: screenshot, scrape, check")
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
