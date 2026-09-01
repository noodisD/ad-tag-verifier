"""
Fuelclient — CB verification. Loads test URL, clicks article, waits for CB overlay.
"""
import re, time, os
from playwright.sync_api import sync_playwright

STATE_FILE = r"./session_state.json"
SHOT_DIR   = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

CM360_DDM  = 'ad.doubleclick.net/ddm/'
DV_PATTERN = 'doubleverify.com'

ACCEPT_SELECTORS = [
    'button:has-text("Akceptuję i przechodzę do serwisu")',
    'button:has-text("Akceptuj wszystkie i przejdź")',
    'button:has-text("Akceptuję wszystkie")',
    'button:has-text("Akceptuj wszystkie")',
    'button:has-text("Akceptuję")',
    '#didomi-notice-agree-button',
]

def accept_cookies(page):
    for sel in ACCEPT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click(); time.sleep(1.5); return True
        except Exception: pass
    return False

SLOTS = [
    ("CB_desktop", "1725483",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=desktop_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725483%22%7D%5D&testPos=2",
     {"width": 1280, "height": 800},
     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
     False),

    ("CB_mobile", "1725484",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=mobile_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725484%22%7D%5D&testPos=2",
     {"width": 390, "height": 844},
     "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36",
     True),
]

def check_cb(pw, label, slot_id, url, viewport, ua, mobile):
    cm_found, dv_found = [], []

    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        storage_state=STATE_FILE, viewport=viewport, user_agent=ua,
        locale="pl-PL", is_mobile=mobile, has_touch=mobile)

    def on_req(req):
        u = req.url
        if CM360_DDM in u  and u not in cm_found: cm_found.append(u)
        if DV_PATTERN in u and u not in dv_found: dv_found.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    # 1. Load test URL
    print(f"\n[{label}] Ładowanie strony testowej…")
    page.goto(url, wait_until="domcontentloaded", timeout=35000)
    time.sleep(3)
    accept_cookies(page)
    time.sleep(4)

    # 2. Find any article link on the page and click it
    # CB fires on navigation, so we need a real click on an article
    clicked = False
    selectors = [
        'a[href*="wiadomosci.wp.pl/"][href*="-"]',
        'a[href*="wp.pl/"][href*="-"]',
        'h2 a[href]', 'h3 a[href]',
        'article a[href]',
        '.sc-bdVTJa a[href]',
        '.teaserTitle a',
    ]
    for sel in selectors:
        try:
            links = page.locator(sel)
            for i in range(min(links.count(), 5)):
                href = links.nth(i).get_attribute("href") or ""
                if ("wp.pl" in href or "pudelek.pl" in href) and len(href) > 30:
                    print(f"  [klik] {href[:90]}")
                    links.nth(i).click()
                    clicked = True
                    break
            if clicked:
                break
        except Exception:
            pass

    if not clicked:
        print("  [brak linku] próba JavaScript click na pierwszym artykule…")
        try:
            page.evaluate("""
                const links = Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => a.href.includes('wp.pl') && a.href.includes('-') && a.href.length > 50);
                if (links.length) links[0].click();
            """)
            clicked = True
        except Exception as e:
            print(f"  [JS click ERR] {e}")

    # 3. Wait for CB overlay and tracking
    print(f"  [czekam] 35s na CB i tagi…")
    time.sleep(35)

    # Screenshot po CB
    shot = os.path.join(SHOT_DIR, f"{label}_cb.png")
    page.screenshot(path=shot)
    print(f"  [screenshot] {shot}")

    ctx.close(); browser.close()

    cm_ok = bool(cm_found)
    dv_ok = bool(dv_found)
    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"\n  === WYNIK [{label}] slot={slot_id} ===")
    print(f"  CM360 ({len(cm_found)}): {'✅' if cm_ok else '❌'}")
    for u in cm_found[:5]: print(f"    {u[:130]}")
    print(f"  DV    ({len(dv_found)}): {'✅' if dv_ok else '❌'}")
    for u in dv_found[:3]: print(f"    {u[:130]}")
    print(f"  → STATUS: {status}")

    return {"label": label, "slot": slot_id, "cm360": cm_ok, "dv": dv_ok, "status": status,
            "cm_urls": cm_found, "dv_urls": dv_found}

def run():
    results = []
    with sync_playwright() as pw:
        for label, slot_id, url, viewport, ua, mobile in SLOTS:
            r = check_cb(pw, label, slot_id, url, viewport, ua, mobile)
            results.append(r)

    print(f"\n{'='*60}")
    print(f"{'Label':<20} {'Slot':<10} CM360  DV    Status")
    print("-"*60)
    for r in results:
        print(f"{r['label']:<20} {r['slot']:<10} {'✅' if r['cm360'] else '❌'}      {'✅' if r['dv'] else '❌'}     {r['status']}")

if __name__ == "__main__":
    run()
