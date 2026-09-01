"""
Otwiera pudelek.pl test URL i monitoruje tagi przez 3 minuty.
Ty klikasz w przeglądarce — skrypt raportuje CM360 i DV na bieżąco.
"""
import time
from playwright.sync_api import sync_playwright

TEST_URL = "https://www.pudelek.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=300_600_desktop&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725498%22%7D%5D&testPos=36"

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

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        locale="pl-PL")

    cm_found, dv_found = [], []

    def on_req(req):
        u = req.url
        if CM360_DDM in u and u not in cm_found:
            cm_found.append(u)
            print(f"\n  ✅ CM360: {u[:140]}")
        if DV_PATTERN in u and u not in dv_found:
            dv_found.append(u)
            print(f"  ✅ DV:    {u[:140]}")

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    print("Ładuję pudelek.pl…")
    page.goto(TEST_URL, wait_until="domcontentloaded", timeout=35000)
    time.sleep(3)
    accept_cookies(page)

    print("\n" + "="*60)
    print("PRZEGLĄDARKA OTWARTA — klikaj w kreację na stronie!")
    print("Monitoring przez 3 minuty…")
    print("="*60)

    for i in range(18):  # 18 x 10s = 3 min
        time.sleep(10)
        remaining = 180 - (i+1)*10
        print(f"  [{180-(i)*10}s pozostało] CM360: {len(cm_found)} | DV: {len(dv_found)}", end="\r")

    print(f"\n\nKoniec monitorowania.")
    print(f"\nWYNIK:")
    print(f"  CM360 ({len(cm_found)}): {'✅' if cm_found else '❌'}")
    for u in cm_found: print(f"    {u[:140]}")
    print(f"  DV    ({len(dv_found)}): {'✅' if dv_found else '❌'}")

    status = "PASS" if (cm_found and dv_found) else ("CM_ONLY" if cm_found else ("DV_ONLY" if dv_found else "FAIL"))
    print(f"  → STATUS: {status}")

    ctx.close()
    browser.close()
