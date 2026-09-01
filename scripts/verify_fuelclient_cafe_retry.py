"""
Fuelclient cafe — retry CM360 check for 5 missing slots
Mobile placements use mobile viewport; CB gets extra wait time.
"""

import re, time, os
from playwright.sync_api import sync_playwright

STATE_FILE = r"./session_state.json"

CM360_PATTERNS = [
    'ad.doubleclick.net/ddm/trackimp',
    'ad.doubleclick.net/ddm/trackclk',
    'ad.doubleclick.net/ddm/jump',
    'ad.doubleclick.net/ddm/clk',
    'ad.doubleclick.net/ddm/kimpj',
    'ad.doubleclick.net/ddm/kclk',
    'googleads.g.doubleclick.net',
]
DV_PATTERNS = ['pub.doubleverify.com', 'cdn.doubleverify.com', 'tps.doubleverify.com']

def is_cm360(url): return any(p in url for p in CM360_PATTERNS)
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

# Slots to retry: (label, slot_id, url, viewport, wait_sec)
RETRY = [
    ("CB_desktop",    "1725483",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=desktop_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725483%22%7D%5D&testPos=2",
     {"width": 1280, "height": 800}, "desktop",
     25),

    ("CB_mobile",     "1725484",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=mobile_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725484%22%7D%5D&testPos=2",
     {"width": 390, "height": 844}, "mobile",
     25),

    ("600x400_mobile","1725485",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=600_400_mobile&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725485%22%7D%5D&testPos=1",
     {"width": 390, "height": 844}, "mobile",
     20),

    ("600x200_mobile","1725486",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=600_200_mobile&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725486%22%7D%5D&testPos=1",
     {"width": 390, "height": 844}, "mobile",
     20),

    ("300x600_desktop","1725498",
     "https://www.pudelek.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=300_600_desktop&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725498%22%7D%5D&testPos=36",
     {"width": 1280, "height": 800}, "desktop",
     20),
]

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
UA_MOBILE  = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36"

def check(pw, label, slot_id, url, viewport, vp_type, wait_sec):
    ua = UA_MOBILE if vp_type == "mobile" else UA_DESKTOP
    found_cm360, found_dv = [], []

    browser = pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE_FILE, viewport=viewport,
                               user_agent=ua, locale="pl-PL",
                               is_mobile=(vp_type == "mobile"),
                               has_touch=(vp_type == "mobile"))

    def on_req(req):
        u = req.url
        if is_cm360(u) and u not in found_cm360: found_cm360.append(u)
        if is_dv(u)    and u not in found_dv:    found_dv.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [WARN] {e}")

    time.sleep(2)
    accept_cookies(page)
    time.sleep(wait_sec)

    ctx.close(); browser.close()

    cm_ok = bool(found_cm360)
    dv_ok = bool(found_dv)
    cm_short = found_cm360[0][:130] if found_cm360 else "—"
    dv_short = found_dv[0][:130]  if found_dv  else "—"
    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"\n[{label}] slot={slot_id} viewport={vp_type}")
    print(f"  CM360: {'✅' if cm_ok else '❌'}  {cm_short}")
    print(f"  DV:    {'✅' if dv_ok else '❌'}  {dv_short}")
    print(f"  → {status}")
    return {"label": label, "slot": slot_id, "vp": vp_type,
            "cm360": cm_ok, "cm_url": cm_short, "dv": dv_ok, "dv_url": dv_short, "status": status}

def run():
    results = []
    with sync_playwright() as pw:
        for label, slot_id, url, viewport, vp_type, wait_sec in RETRY:
            r = check(pw, label, slot_id, url, viewport, vp_type, wait_sec)
            results.append(r)

    print("\n" + "=" * 80)
    print(f"{'Label':<20} {'Slot':<10} {'VP':<8} {'CM360':>6} {'DV':>6}  Status")
    print("-" * 80)
    for r in results:
        print(f"{r['label']:<20} {r['slot']:<10} {r['vp']:<8} {'✅' if r['cm360'] else '❌':>6} {'✅' if r['dv'] else '❌':>6}  {r['status']}")

if __name__ == "__main__":
    run()
