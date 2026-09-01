"""Debug DV on Gazeta desktop — dump all doubleverify + all iframe sources."""
import re, time
from playwright.sync_api import sync_playwright

URL = "https://www.gazeta.pl/0,0.html?google_preview=PLACEHOLDER&iu=90000001&gdfp_req=1&lineItemId=9000000201&creativeId=900000035240"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

ACCEPT = ['button:has-text("AKCEPTUJĘ")', 'button:has-text("Akceptuję")']

all_reqs = []

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width":1280,"height":800}, user_agent=UA, locale="pl-PL")

        def on_req(req):
            u = req.url
            if 'doubleverify' in u.lower() or 'doubleclick' in u.lower() or 'dvbm' in u.lower():
                all_reqs.append(u)
                print(f"  REQ: {u[:130]}")

        page = ctx.new_page()
        page.on("request", on_req)
        ctx.on("request", on_req)

        page.goto(URL, wait_until="domcontentloaded", timeout=35000)
        time.sleep(4)

        for sel in ACCEPT:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click(); time.sleep(2); break
            except Exception: pass

        time.sleep(30)

        # Also scan all frame HTML
        print("\n--- SCANNING FRAMES FOR DV ---")
        for i, frame in enumerate(page.frames):
            try:
                html = frame.content()
                if 'doubleverify' in html.lower() or 'dvbm' in html.lower():
                    print(f"\n  [Frame {i}: {frame.url[:80]}] HAS DV!")
                    matches = re.findall(r'[^\s"\'<>]{0,40}doubleverify[^\s"\'<>]{0,100}', html, re.IGNORECASE)
                    for m in matches[:5]:
                        print(f"    {m}")
            except Exception: pass

        print(f"\nTotal CM360/DV requests captured: {len(all_reqs)}")
        dv_req = [r for r in all_reqs if 'doubleverify' in r.lower()]
        print(f"DV requests: {len(dv_req)}")
        for r in dv_req:
            print(f"  {r[:130]}")

        ctx.close(); browser.close()

if __name__ == "__main__":
    run()
