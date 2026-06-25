#!/usr/bin/env python3
"""colab-auto.py — Playwright: auto Colab training setup."""
import sys, io, time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DATA_FILE = Path(r"C:\Users\z1439\OneDrive\Desktop\模型\brain_dataset.jsonl")
CODE = Path(r"C:\Users\z1439\OneDrive\Desktop\模型\colab_run.py").read_text(encoding="utf-8")

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print("1/5 Opening Colab...")
    page.goto("https://colab.research.google.com/", timeout=30000)
    time.sleep(5)

    # Just find ANY clickable element to focus the page, then use keyboard
    print("2/5 Creating notebook via keyboard...")
    page.keyboard.press("Control+a")  # focus page
    time.sleep(1)
    # Try clicking the first visible button/link to bypass welcome screen
    page.evaluate("""() => {
        // Click "New notebook" if visible
        const btns = document.querySelectorAll('a, button, [role="button"]');
        for (const b of btns) {
            if (b.textContent.includes('ew notebook') || b.textContent.includes('新建')) {
                b.click(); return 'clicked';
            }
        }
        // Fallback: open blank notebook URL
        window.location.href = 'https://colab.research.google.com/#create=true';
        return 'fallback_url';
    }""")
    time.sleep(5)

    print("3/5 Setting T4 GPU via eval...")
    page.evaluate("""() => {
        // Click Runtime menu
        const menus = document.querySelectorAll('#runtime-menu-button, [data-test-id="runtime-menu-button"], .runtime-selector');
        for (const m of menus) { m.click(); break; }
    }""")
    time.sleep(2)
    page.evaluate("""() => {
        // Find and click "Change runtime type"
        const items = document.querySelectorAll('span, div, li, a, button');
        for (const i of items) {
            if (i.textContent.includes('hange runtime') || i.textContent.includes('更改运行时')) {
                i.click(); return;
            }
        }
    }""")
    time.sleep(3)
    # Select GPU
    page.evaluate("""() => {
        const selects = document.querySelectorAll('select');
        for (const s of selects) {
            const opts = s.querySelectorAll('option');
            for (const o of opts) {
                if (o.value === 'gpu' || o.textContent.includes('T4') || o.textContent.includes('GPU')) {
                    s.value = o.value;
                    s.dispatchEvent(new Event('change', {bubbles: true}));
                    return;
                }
            }
        }
    }""")
    time.sleep(1)
    # Click Save
    page.evaluate("""() => {
        const btns = document.querySelectorAll('button, input[type="submit"]');
        for (const b of btns) {
            if (b.textContent.includes('Save') || b.textContent.includes('保存')) {
                b.click(); return;
            }
        }
    }""")
    time.sleep(3)

    print("4/5 Pasting code...")
    # Focus code cell
    page.evaluate("""() => {
        const cells = document.querySelectorAll('.CodeMirror');
        if (cells.length > 0) cells[0].CodeMirror.setValue('');
    }""")
    time.sleep(1)
    page.keyboard.type(CODE)
    time.sleep(1)

    print("5/5 Running! Browser stays open for file upload.")
    page.keyboard.press("Control+Enter")
    time.sleep(10)

    # Handle file upload when dialog appears
    try:
        page.locator('input[type="file"]').set_input_files(str(DATA_FILE))
        print(f"Uploaded brain dataset ({DATA_FILE.stat().st_size} bytes)")
    except:
        print("Upload dialog may appear later — drag brain_dataset.jsonl when prompted")

    print("\n✅ Training started. Keep browser open ~15 min.")
    print("Result auto-downloads as ralph-qwen-1.5b.zip")
    input("Press Enter when done to close browser...")
    browser.close()
