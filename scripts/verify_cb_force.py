"""
Fuelclient CB — aggressively clicks multiple articles until Fuelclient CB fires.
Uses fresh context (no frequency cap) each attempt.
"""
import re, time, os
from playwright.sync_api import sync_playwright

SHOT_DIR = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

CM360_DDM  = 'ad.doubleclick.net/ddm/'
DV_PATTERN = 'doubleverify.com'

CB_URLS = {
    "CB_desktop": (
        "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=desktop_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725483%22%7D%5D&testPos=2",
        {"width": 1280, "height": 800},
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        False
    ),
    "CB_mobile": (
        "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=mobile_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725484%22%7D%5D&testPos=2",
        {"width": 390, "height": 844},
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36",
        True
    ),
}

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

def get_article_links(page):
    """Extract wp.pl article links from current page."""
    links = []
    try:
        hrefs = page.eval_on_selector_all(
            'a[href]',
            'els => els.map(e => e.href)'
        )
        for h in hrefs:
            if (('wp.pl/' in h or 'pudelek.pl/' in h) and
                len(h) > 40 and
                not any(x in h for x in ['.jpg','.png','.gif','javascript:','#','reklama','advert','wfName','premium','mailto'])):
                links.append(h)
        links = list(dict.fromkeys(links))  # dedupe preserving order
    except Exception:
        pass
    return links

def run_cb(pw, label, test_url, viewport, ua, mobile):
    cm_found, dv_found = [], []
    print(f"\n{'='*60}")
    print(f"[{label}] Start — fresh context, klikam artykuły jeden po drugim…")

    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    # Fresh context — NO stored state = no frequency cap
    ctx = browser.new_context(
        viewport=viewport, user_agent=ua, locale="pl-PL",
        is_mobile=mobile, has_touch=mobile)

    def on_req(req):
        u = req.url
        if CM360_DDM  in u and u not in cm_found: cm_found.append(u)
        if DV_PATTERN in u and u not in dv_found: dv_found.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    # Load test URL
    print(f"  Ładuję test URL…")
    page.goto(test_url, wait_until="domcontentloaded", timeout=35000)
    time.sleep(3)
    accept_cookies(page)
    time.sleep(4)

    # Collect article links from landing page
    links = get_article_links(page)
    print(f"  Znaleziono {len(links)} linków do artykułów")

    MAX_CLICKS = 8
    for i in range(min(len(links), MAX_CLICKS)):
        before_cm = len(cm_found)

        # Re-collect links from current page (after each back-navigation)
        current_links = get_article_links(page)
        if not current_links:
            print(f"  [{i+1}] Brak linków na stronie, przerywam")
            break

        href = current_links[i] if i < len(current_links) else current_links[0]
        print(f"  [{i+1}/{min(len(links), MAX_CLICKS)}] Klikam (realny klik): {href[:80]}")

        try:
            # Real click — fires JS event handlers that WP uses to trigger CB
            link = page.locator(f'a[href="{href}"]').first
            if link.count() == 0:
                link = page.locator(f'a[href*="{href[-30:]}"]').first
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                link.click()
        except Exception:
            # Fallback: JS click to preserve event chain
            try:
                page.evaluate(f'document.querySelector(\'a[href="{href}"]\').click()')
                time.sleep(3)
            except Exception as e2:
                print(f"    [WARN] {e2}")
                continue

        time.sleep(2)
        accept_cookies(page)
        time.sleep(12)  # wait for CB overlay and tracking

        if len(cm_found) > before_cm:
            print(f"  ✅ CM360 znaleziony po kliknięciu artykułu #{i+1}!")
            shot = os.path.join(SHOT_DIR, f"{label}_found.png")
            page.screenshot(path=shot)
            print(f"  Screenshot: {shot}")
            break
        else:
            print(f"    CM360 nie odpalił na tej stronie")

        # Back to test URL for next attempt
        if i < min(len(links), MAX_CLICKS) - 1:
            print(f"    Wracam na stronę testową…")
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                    page.go_back()
                time.sleep(3)
            except Exception:
                try:
                    page.goto(test_url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(3)
                except Exception:
                    pass

    # Final screenshot
    shot_final = os.path.join(SHOT_DIR, f"{label}_final.png")
    try: page.screenshot(path=shot_final)
    except Exception: pass

    ctx.close(); browser.close()

    cm_ok = bool(cm_found)
    dv_ok = bool(dv_found)
    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"\n  WYNIK [{label}]")
    print(f"  CM360 ({len(cm_found)}): {'✅' if cm_ok else '❌'}")
    for u in cm_found[:5]: print(f"    {u[:130]}")
    print(f"  DV    ({len(dv_found)}): {'✅' if dv_ok else '❌'}")
    print(f"  → STATUS: {status}")
    return {"label": label, "cm360": cm_ok, "dv": dv_ok, "status": status, "cm_urls": cm_found}

def run():
    results = []
    with sync_playwright() as pw:
        for label, (url, vp, ua, mob) in CB_URLS.items():
            r = run_cb(pw, label, url, vp, ua, mob)
            results.append(r)

    print(f"\n{'='*60}")
    print("FINALNY WYNIK CB")
    print(f"{'Label':<20} CM360  DV    Status")
    print("-"*50)
    for r in results:
        print(f"{r['label']:<20} {'✅' if r['cm360'] else '❌'}      {'✅' if r['dv'] else '❌'}     {r['status']}")

if __name__ == "__main__":
    run()
