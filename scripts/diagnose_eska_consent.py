"""Quick diagnostic — find eska.pl consent button selector"""
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = ctx.new_page()
    page.goto("https://www.eska.pl/", wait_until="domcontentloaded", timeout=25000)
    page.bring_to_front()
    time.sleep(5)

    print("\n=== MAIN PAGE BUTTONS ===")
    buttons = page.evaluate("""() => {
        const btns = [];
        document.querySelectorAll('button').forEach(b => {
            const txt = b.innerText.trim();
            const cls = b.className;
            const id = b.id;
            if (txt || id) btns.push({text: txt.slice(0,80), class: cls.slice(0,80), id: id});
        });
        return btns;
    }""")
    for b in buttons:
        print(f"  text='{b['text']}'  id='{b['id']}'  class='{b['class']}'")

    print("\n=== IFRAMES ===")
    for frame in page.frames:
        if frame == page.main_frame: continue
        print(f"\n  Frame: {frame.url[:80]}")
        try:
            btns = frame.evaluate("""() => {
                const btns = [];
                document.querySelectorAll('button').forEach(b => {
                    const txt = b.innerText.trim();
                    const id = b.id;
                    const cls = b.className;
                    if (txt || id) btns.push({text: txt.slice(0,80), class: cls.slice(0,80), id: id});
                });
                return btns;
            }""")
            for b in btns:
                print(f"    text='{b['text']}'  id='{b['id']}'  class='{b['class']}'")
        except Exception as e:
            print(f"    [error] {e}")

    input("\nPress Enter to close...")
    browser.close()
