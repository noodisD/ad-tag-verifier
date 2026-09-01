"""CB_mobile only retry with fixed link extraction."""
import re, time, os
from playwright.sync_api import sync_playwright

SHOT_DIR = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

# Strict: only real CB mobile placement IDs from Excel
CM360_CB_MOBILE = ['900000010', '900000022']
CM360_DDM  = 'ad.doubleclick.net/ddm/'
DV_PATTERN = 'doubleverify.com'

def is_cb_mobile_cm360(url):
    """Only count CM360 tags that match CB mobile placement IDs."""
    return CM360_DDM in url and any(pid in url for pid in CM360_CB_MOBILE)

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

TEST_URL = "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=mobile_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725484%22%7D%5D&testPos=2"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36"
VP = {"width": 390, "height": 844}

def run():
    cm_found, dv_found = [], []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False,
                                      args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport=VP, user_agent=UA, locale="pl-PL",
                                   is_mobile=True, has_touch=True)

        def on_req(req):
            u = req.url
            if is_cb_mobile_cm360(u) and u not in cm_found:
                cm_found.append(u)
                print(f"\n  *** CB MOBILE CM360 WYKRYTY: {u[:130]}")
            elif CM360_DDM in u:
                pid = next((p for p in ['900000034','900000037','900000045','900000057','900000066','900000022','900000079','900000010'] if p in u), '?')
                print(f"  [inny placement={pid}]: {u[:100]}")
            if DV_PATTERN in u and u not in dv_found: dv_found.append(u)

        page = ctx.new_page()
        page.on("request", on_req)
        ctx.on("request", on_req)

        print("[CB_mobile] Ładuję test URL…")
        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=35000)
        time.sleep(3)
        accept_cookies(page)
        time.sleep(4)

        # Get ALL links from page
        try:
            all_hrefs = page.evaluate('Array.from(document.querySelectorAll("a[href]")).map(e => e.href)')
        except Exception:
            all_hrefs = []
        links = list(dict.fromkeys([
            h for h in all_hrefs
            if 'wp.pl/' in h and len(h) > 40
            and not any(x in h for x in ['.jpg','.png','javascript:','#','mailto','wfName','premium'])
        ]))
        print(f"  Znaleziono {len(links)} linków")

        # Debug: show first 10
        for l in links[:10]:
            print(f"    {l[:90]}")

        for i, href in enumerate(links[:8]):
            before_cm = len(cm_found)
            print(f"\n  [{i+1}/8] Klikam: {href[:80]}")
            try:
                link = page.locator(f'a[href="{href}"]').first
                if link.count() == 0:
                    # Try partial match on last segment
                    seg = href.split('/')[-1]
                    link = page.locator(f'a[href$="{seg}"]').first
                with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                    link.click()
            except Exception as e:
                print(f"    [WARN] {e} — próba JS click")
                try:
                    page.evaluate(f"""
                        var links = Array.from(document.querySelectorAll('a[href]'));
                        var match = links.find(a => a.href === '{href}');
                        if (match) match.click();
                    """)
                    time.sleep(3)
                except Exception as e2:
                    print(f"    [JS ERR] {e2}")
                    continue

            time.sleep(2)
            accept_cookies(page)
            time.sleep(12)

            shot = os.path.join(SHOT_DIR, f"CB_mobile_click{i+1}.png")
            page.screenshot(path=shot)
            print(f"    Screenshot: {shot}")

            if len(cm_found) > before_cm:
                print(f"  ✅ CM360 znaleziony po kliknięciu #{i+1}!")
                break
            else:
                print(f"    CM360 nie odpalił")
                try:
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                        page.go_back()
                    time.sleep(3)
                except Exception:
                    page.goto(TEST_URL, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(3)

        ctx.close(); browser.close()

    cm_ok = bool(cm_found)
    dv_ok = bool(dv_found)
    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))
    print(f"\nWYNIK CB_mobile: CM360={'✅' if cm_ok else '❌'} DV={'✅' if dv_ok else '❌'} → {status}")
    for u in cm_found[:3]: print(f"  {u[:130]}")

if __name__ == "__main__":
    run()
