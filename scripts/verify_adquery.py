"""Adquery push preview — CM360 + DV tag check."""
import re, time, os
from playwright.sync_api import sync_playwright

SHOT_DIR = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

CM360_DDM  = 'ad.doubleclick.net/ddm/'
DV_PATTERN = 'doubleverify.com'

URLS = [
    ("Adquery_1", "https://backend.adquery.io/push-preview/MzE4MzY="),
    ("Adquery_2", "https://backend.adquery.io/push-preview/MzE4Mzc="),
    ("Adquery_3", "https://backend.adquery.io/push-preview/MzE4Mzg="),
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

def check(pw, label, url):
    cm_found, dv_found = [], []

    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, user_agent=UA)

    def on_req(req):
        u = req.url
        if CM360_DDM  in u and u not in cm_found: cm_found.append(u)
        if DV_PATTERN in u and u not in dv_found: dv_found.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    print(f"\n[{label}] {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  [WARN] {e}")

    time.sleep(8)  # wait for all tracking to fire

    # Screenshot
    shot = os.path.join(SHOT_DIR, f"{label}.png")
    try: page.screenshot(path=shot); print(f"  Screenshot: {shot}")
    except Exception: pass

    # Also scan page HTML for embedded tags
    for frame in page.frames:
        try:
            html = frame.content()
            cm_hits = re.findall(r'https?://ad\.doubleclick\.net/ddm/[^\s"\']{0,150}', html)
            dv_hits = re.findall(r'https?://[^\s"\']*doubleverify\.com[^\s"\']{0,120}', html)
            for h in cm_hits:
                if h not in cm_found: cm_found.append(f"[html] {h}")
            for h in dv_hits:
                if h not in dv_found: dv_found.append(f"[html] {h}")
        except Exception: pass

    ctx.close(); browser.close()

    cm_ok = bool(cm_found)
    dv_ok = bool(dv_found)
    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"  CM360 ({len(cm_found)}): {'✅' if cm_ok else '❌'}  {cm_found[0][:120] if cm_found else '—'}")
    print(f"  DV    ({len(dv_found)}): {'✅' if dv_ok else '❌'}  {dv_found[0][:120] if dv_found else '—'}")
    print(f"  → {status}")

    return {"label": label, "cm360": cm_ok, "dv": dv_ok, "status": status,
            "cm_urls": cm_found, "dv_urls": dv_found}

def run():
    results = []
    with sync_playwright() as pw:
        for label, url in URLS:
            results.append(check(pw, label, url))

    print(f"\n{'='*60}")
    print(f"{'Label':<15} CM360  DV    Status")
    print("-"*50)
    for r in results:
        print(f"{r['label']:<15} {'✅' if r['cm360'] else '❌'}      {'✅' if r['dv'] else '❌'}     {r['status']}")

if __name__ == "__main__":
    run()
