"""
Fuelclient — final verification for 3 slots.
- STRICT CM360 pattern: only ad.doubleclick.net/ddm/ (not GPT/GAM)
- CB: clicks into article first to trigger the between-pages ad
- 300x600: scrolls to make slot visible
- Screenshots saved for proof
"""

import re, time, os
from playwright.sync_api import sync_playwright

STATE_FILE = r"./session_state.json"
SHOT_DIR   = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

# STRICT: only real CM360 DDM tracking tags, not GPT/publisher infra
CM360_DDM = 'ad.doubleclick.net/ddm/'

DV_PATTERNS = ['pub.doubleverify.com', 'cdn.doubleverify.com', 'tps.doubleverify.com']

def is_cm360(url): return CM360_DDM in url
def is_dv(url):    return any(p in url for p in DV_PATTERNS)

ACCEPT_SELECTORS = [
    'button:has-text("Akceptuję i przechodzę do serwisu")',
    'button:has-text("Akceptuj wszystkie i przejdź")',
    'button:has-text("Akceptuję wszystkie")',
    'button:has-text("Akceptuj wszystkie")',
    'button:has-text("Akceptuję")',
    '#didomi-notice-agree-button',
    'button[class*="accept"]',
]

def accept_cookies(page):
    for sel in ACCEPT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click(); time.sleep(1); return True
        except Exception: pass
    for frame in page.frames:
        if not frame.url: continue
        for sel in ACCEPT_SELECTORS:
            try:
                btn = frame.locator(sel).first
                if btn.is_visible(timeout=500):
                    btn.click(); time.sleep(1); return True
            except Exception: pass
    return False

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
UA_MOBILE  = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36"


def check_cb(pw, label, slot_id, url, viewport, vp_type):
    """CB format: navigate to page, click first article link to trigger between-pages ad."""
    ua = UA_MOBILE if vp_type == "mobile" else UA_DESKTOP
    cm_found, dv_found = [], []

    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        storage_state=STATE_FILE, viewport=viewport,
        user_agent=ua, locale="pl-PL",
        is_mobile=(vp_type == "mobile"), has_touch=(vp_type == "mobile"))

    def on_req(req):
        u = req.url
        if is_cm360(u) and u not in cm_found: cm_found.append(u)
        if is_dv(u)    and u not in dv_found: dv_found.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    # Step 1: load the test URL (sets up the slot context)
    print(f"  [1] Loading test URL…")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [WARN] {e}")
    time.sleep(3)
    accept_cookies(page)
    time.sleep(5)

    # Step 2: click first article link to trigger CB between-pages
    print(f"  [2] Clicking article link to trigger CB…")
    article_clicked = False
    article_selectors = [
        'a[href*="wiadomosci.wp.pl"]',
        'a[href*="wp.pl"][class*="article"]',
        'article a[href]',
        'h2 a[href]',
        'h3 a[href]',
        '.title a',
        '.sc-article a',
    ]
    for sel in article_selectors:
        try:
            links = page.locator(sel)
            count = links.count()
            if count > 0:
                href = links.first.get_attribute("href") or ""
                if href and "wp.pl" in href and not href.endswith(".jpg") and not href.endswith(".png"):
                    print(f"     clicking: {href[:80]}")
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                        links.first.click()
                    article_clicked = True
                    break
        except Exception:
            pass

    if not article_clicked:
        print("  [2] No article link found, trying direct nav to wiadomosci.wp.pl…")
        try:
            page.goto("https://wiadomosci.wp.pl/", wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)
            links = page.locator("h2 a, h3 a, .teaserTitle a, article a")
            if links.count() > 0:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                    links.first.click()
                article_clicked = True
        except Exception as e:
            print(f"  [2 WARN] {e}")

    time.sleep(3)
    accept_cookies(page)

    # Step 3: wait for CB overlay and tracking to fire
    print(f"  [3] Waiting 30s for CB ad and tracking…")
    time.sleep(30)

    # Screenshot
    shot = os.path.join(SHOT_DIR, f"{label}_deep.png")
    try: page.screenshot(path=shot); print(f"  [screenshot] {shot}")
    except Exception as e: print(f"  [screenshot ERR] {e}")

    # Also check iframes
    for frame in page.frames:
        fu = frame.url or ""
        if is_cm360(fu) and fu not in cm_found: cm_found.append(f"[frame_src] {fu}")
        if is_dv(fu)    and fu not in dv_found: dv_found.append(f"[frame_src] {fu}")
        try:
            html = frame.content()
            if is_cm360(html):
                hits = re.findall(r'https?://ad\.doubleclick\.net/ddm/[^\s"\']{0,150}', html)
                for h in hits:
                    if h not in cm_found: cm_found.append(f"[frame_html] {h}")
        except Exception: pass

    ctx.close(); browser.close()

    cm_ok = bool(cm_found)
    dv_ok = bool(dv_found)
    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"\n  RESULT [{label}] slot={slot_id} vp={vp_type}")
    print(f"  CM360 ({len(cm_found)}): {cm_found[0][:130] if cm_found else '—'}")
    print(f"  DV    ({len(dv_found)}): {dv_found[0][:130] if dv_found else '—'}")
    print(f"  → {status}")
    return {"label": label, "slot": slot_id, "vp": vp_type,
            "cm360": cm_ok, "dv": dv_ok, "status": status,
            "cm_all": cm_found, "dv_all": dv_found}


def check_banner(pw, label, slot_id, url, viewport, vp_type):
    """Banner: scroll to make slot visible, wait for ad and tracking."""
    ua = UA_MOBILE if vp_type == "mobile" else UA_DESKTOP
    cm_found, dv_found = [], []

    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        storage_state=STATE_FILE, viewport=viewport,
        user_agent=ua, locale="pl-PL",
        is_mobile=(vp_type == "mobile"), has_touch=(vp_type == "mobile"))

    def on_req(req):
        u = req.url
        if is_cm360(u) and u not in cm_found: cm_found.append(u)
        if is_dv(u)    and u not in dv_found: dv_found.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [WARN] {e}")

    time.sleep(3)
    accept_cookies(page)
    time.sleep(5)

    # Scroll slowly to make banner visible
    for _ in range(10):
        page.keyboard.press("PageDown")
        time.sleep(1.5)

    time.sleep(20)

    shot = os.path.join(SHOT_DIR, f"{label}_deep.png")
    try: page.screenshot(path=shot); print(f"  [screenshot] {shot}")
    except Exception as e: print(f"  [screenshot ERR] {e}")

    for frame in page.frames:
        fu = frame.url or ""
        if is_cm360(fu) and fu not in cm_found: cm_found.append(f"[frame_src] {fu}")
        try:
            html = frame.content()
            if is_cm360(html):
                hits = re.findall(r'https?://ad\.doubleclick\.net/ddm/[^\s"\']{0,150}', html)
                for h in hits:
                    if h not in cm_found: cm_found.append(f"[frame_html] {h}")
        except Exception: pass

    ctx.close(); browser.close()

    cm_ok = bool(cm_found)
    dv_ok = bool(dv_found)
    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"\n  RESULT [{label}] slot={slot_id} vp={vp_type}")
    print(f"  CM360 ({len(cm_found)}): {cm_found[0][:130] if cm_found else '—'}")
    print(f"  DV    ({len(dv_found)}): {dv_found[0][:130] if dv_found else '—'}")
    print(f"  → {status}")
    return {"label": label, "slot": slot_id, "vp": vp_type,
            "cm360": cm_ok, "dv": dv_ok, "status": status,
            "cm_all": cm_found, "dv_all": dv_found}


def run():
    results = []
    with sync_playwright() as pw:
        results.append(check_cb(pw, "CB_desktop", "1725483",
            "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=desktop_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725483%22%7D%5D&testPos=2",
            {"width": 1280, "height": 800}, "desktop"))

        results.append(check_cb(pw, "CB_mobile", "1725484",
            "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=mobile_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725484%22%7D%5D&testPos=2",
            {"width": 390, "height": 844}, "mobile"))

        results.append(check_banner(pw, "300x600_desktop", "1725498",
            "https://www.pudelek.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=300_600_desktop&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725498%22%7D%5D&testPos=36",
            {"width": 1280, "height": 800}, "desktop"))

    print(f"\n{'='*70}")
    print("FINALNY WYNIK")
    print(f"{'Label':<22} {'Slot':<10} CM360  DV    Status")
    print("-"*60)
    for r in results:
        print(f"{r['label']:<22} {r['slot']:<10} {'✅' if r['cm360'] else '❌'}      {'✅' if r['dv'] else '❌'}     {r['status']}")
        if r['cm_all']:
            for u in r['cm_all'][:3]: print(f"  CM: {u[:120]}")
        if r['dv_all']:
            for u in r['dv_all'][:2]: print(f"  DV: {u[:120]}")

if __name__ == "__main__":
    run()
