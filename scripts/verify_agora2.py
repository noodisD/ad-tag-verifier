"""Agora — Gazeta.pl + Sport.pl CM360 + DV check."""
import re, time, os
from playwright.sync_api import sync_playwright

SHOT_DIR = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

CM360_DDM  = 'ad.doubleclick.net/ddm/'
DV_PATTERN = 'doubleverify.com'

UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36"

PLACEMENTS = [
    ("Gazeta_desktop", {"width":1280,"height":800}, UA_D, False,
     "https://www.gazeta.pl/0,0.html?google_preview=PLACEHOLDER&iu=90000001&gdfp_req=1&lineItemId=9000000201&creativeId=900000035240"),
    ("Gazeta_mobile",  {"width":390,"height":844},  UA_M, True,
     "https://www.gazeta.pl/0,0.html?google_preview=PLACEHOLDER&iu=90000001&gdfp_req=1&lineItemId=9000000201&creativeId=900000035282"),
    ("Sport_desktop",  {"width":1280,"height":800}, UA_D, False,
     "https://www.sport.pl/sport-hp/0,0.html?google_preview=PLACEHOLDER&iu=90000001&gdfp_req=1&lineItemId=9000000400&creativeId=900000055368#s=NavLinks"),
    ("Sport_mobile_1", {"width":390,"height":844},  UA_M, True,
     "https://www.sport.pl/sport-hp/0,0.html?google_preview=PLACEHOLDER&iu=90000001&gdfp_req=1&lineItemId=9000000400&creativeId=900000063764#s=NavLinks"),
    ("Sport_mobile_2", {"width":390,"height":844},  UA_M, True,
     "https://www.sport.pl/sport-hp/0,0.html?google_preview=PLACEHOLDER&iu=90000001&gdfp_req=1&lineItemId=9000000400&creativeId=900000071809#s=NavLinks"),
]

ACCEPT_SELECTORS = [
    'button:has-text("AKCEPTUJĘ")',
    'button:has-text("Akceptuję")',
    'button:has-text("Akceptuj wszystkie")',
    'button:has-text("AKCEPTUJ")',
    '#didomi-notice-agree-button',
    'button.cmp-btn-accept',
]

def accept_cookies(page):
    for sel in ACCEPT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click(); time.sleep(2); return True
        except Exception: pass
    return False

def check(pw, label, viewport, ua, mobile, url):
    cm_found, dv_found = [], []

    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport=viewport, user_agent=ua, locale="pl-PL",
                               is_mobile=mobile, has_touch=mobile)

    def on_req(req):
        u = req.url
        if CM360_DDM  in u and u not in cm_found: cm_found.append(u)
        if DV_PATTERN in u and u not in dv_found: dv_found.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    print(f"\n[{label}]")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  [WARN] {e}")

    time.sleep(3)
    accepted = accept_cookies(page)
    print(f"  Cookies: {accepted}")
    time.sleep(15)

    for frame in page.frames:
        try:
            html = frame.content()
            for h in re.findall(r'https?://ad\.doubleclick\.net/ddm/[^\s"\'<>]{0,150}', html):
                tag = f"[html] {h}"
                if tag not in cm_found: cm_found.append(tag)
            for h in re.findall(r'https?://[^\s"\'<>]*doubleverify\.com[^\s"\'<>]{0,120}', html):
                tag = f"[html] {h}"
                if tag not in dv_found: dv_found.append(tag)
        except Exception: pass

    shot = os.path.join(SHOT_DIR, f"{label}.png")
    try: page.screenshot(path=shot)
    except Exception: pass

    ctx.close(); browser.close()

    cm_ok = bool(cm_found)
    dv_ok = bool(dv_found)

    # Check IMP vs CLK
    imp_ok = any('trackimp' in u for u in cm_found)
    clk_ok = any('trackclk' in u for u in cm_found)

    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"  CM360 IMP: {'✅' if imp_ok else '❌'}  {next((u[:110] for u in cm_found if 'trackimp' in u), '—')}")
    print(f"  CM360 CLK: {'✅' if clk_ok else '❌'}  {next((u[:110] for u in cm_found if 'trackclk' in u), '—')}")
    print(f"  DV:        {'✅' if dv_ok else '❌'}  {dv_found[0][:110] if dv_found else '—'}")
    print(f"  → {status}")

    return {"label": label, "cm360": cm_ok, "imp": imp_ok, "clk": clk_ok,
            "dv": dv_ok, "status": status}

def run():
    results = []
    with sync_playwright() as pw:
        for label, vp, ua, mob, url in PLACEMENTS:
            results.append(check(pw, label, vp, ua, mob, url))

    print(f"\n{'='*70}")
    print(f"{'Label':<22} IMP    CLK    DV     Status")
    print("-"*65)
    for r in results:
        print(f"{r['label']:<22} {'✅' if r['imp'] else '❌'}      {'✅' if r['clk'] else '❌'}      {'✅' if r['dv'] else '❌'}      {r['status']}")

if __name__ == "__main__":
    run()
