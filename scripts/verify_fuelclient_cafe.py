"""
Fuelclient cafe campaign — CM360 + DoubleVerify tag check
Checks: WP.pl placements (7 URLs) + YOC creative JS
"""

import re, time, os, requests, warnings
from playwright.sync_api import sync_playwright

warnings.filterwarnings('ignore')

STATE_FILE = r"./session_state.json"

# CM360 patterns
CM360_PATTERNS = [
    'ad.doubleclick.net/ddm/trackimp',
    'ad.doubleclick.net/ddm/trackclk',
    'ad.doubleclick.net/ddm/jump',
    'ad.doubleclick.net/ddm/clk',
    'ad.doubleclick.net/ddm/kimpj',
    'ad.doubleclick.net/ddm/kclk',
    'googleads.g.doubleclick.net',
    'adservice.google.com',
]

# DoubleVerify patterns
DV_PATTERNS = [
    'pub.doubleverify.com',
    'cdn.doubleverify.com',
    'tps.doubleverify.com',
    'doubleverify.com',
]

def is_cm360(url):
    return any(p in url for p in CM360_PATTERNS)

def is_dv(url):
    return any(p in url for p in DV_PATTERNS)


# ─── WP.pl placements ──────────────────────────────────────────────────────
WP_ROWS = [
    ("CB_desktop",    "wiadomosci.wp.pl", "CB",      "1725483", "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=desktop_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725483%22%7D%5D&testPos=2"),
    ("CB_mobile",     "wiadomosci.wp.pl", "CB",      "1725484", "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=mobile_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725484%22%7D%5D&testPos=2"),
    ("600x400_mobile","wiadomosci.wp.pl", "Baner",   "1725485", "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=600_400_mobile&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725485%22%7D%5D&testPos=1"),
    ("600x200_mobile","wiadomosci.wp.pl", "Baner",   "1725486", "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=600_200_mobile&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725486%22%7D%5D&testPos=1"),
    ("970x300_desktop","wiadomosci.wp.pl","Baner",   "1725494", "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=970_300_desktop&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725494%22%7D%5D&testPos=3"),
    ("300x600_desktop","pudelek.pl",      "Baner",   "1725498", "https://www.pudelek.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=300_600_desktop&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725498%22%7D%5D&testPos=36"),
    ("giga_desktop",  "wiadomosci.wp.pl","Gigaboard","1725499", "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=giga_desktop&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FGigaboard%2F1725499%22%7D%5D&testPos=3"),
]

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
                btn.click()
                time.sleep(1)
                return True
        except Exception:
            pass
    for frame in page.frames:
        if not frame.url:
            continue
        for sel in ACCEPT_SELECTORS:
            try:
                btn = frame.locator(sel).first
                if btn.is_visible(timeout=500):
                    btn.click()
                    time.sleep(1)
                    return True
            except Exception:
                pass
    return False


def setup_cookie_state(pw):
    print("[SETUP] Accepting cookies on wp.pl …")
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    browser = pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, user_agent=ua, locale="pl-PL")
    page = ctx.new_page()
    page.goto("https://www.wp.pl", wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)
    ok = accept_cookies(page)
    print(f"[SETUP] Accepted: {ok}")
    time.sleep(2)
    ctx.storage_state(path=STATE_FILE)
    ctx.close()
    browser.close()


def check_wp_placement(pw, label, site, fmt, slot_id, url):
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    found_cm360 = []
    found_dv = []

    browser = pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE_FILE,
                               viewport={"width": 1280, "height": 800},
                               user_agent=ua, locale="pl-PL")

    def on_req(req):
        u = req.url
        if is_cm360(u) and u not in found_cm360:
            found_cm360.append(u)
        if is_dv(u) and u not in found_dv:
            found_dv.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  [WARN] {e}")

    time.sleep(2)
    accept_cookies(page)
    time.sleep(15)  # wait for ad to load and fire tracking

    ctx.close()
    browser.close()

    cm_ok = len(found_cm360) > 0
    dv_ok = len(found_dv) > 0

    cm_short = found_cm360[0][:120] if found_cm360 else "—"
    dv_short = found_dv[0][:120] if found_dv else "—"

    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))
    print(f"\n[{label}] slot={slot_id} fmt={fmt}")
    print(f"  CM360: {'✅' if cm_ok else '❌'} {cm_short}")
    print(f"  DV:    {'✅' if dv_ok else '❌'} {dv_short}")
    print(f"  → {status}")

    return {"label": label, "site": site, "fmt": fmt, "slot": slot_id,
            "cm360": cm_ok, "cm_url": cm_short,
            "dv": dv_ok, "dv_url": dv_short,
            "status": status}


def check_yoc():
    """Fetch YOC creative JS and scan for CM360 + DV tags."""
    print("\n[YOC] Fetching creative JS …")
    js_url = "https://c.yoc.com/c/cb/R925-rHx6-5h6M.js"
    try:
        r = requests.get(js_url, timeout=15)
        js = r.text
        cm_hits = [p for p in CM360_PATTERNS if p in js]
        dv_hits = [p for p in DV_PATTERNS if p in js]

        # Also search for raw doubleclick/doubleverify URLs in the JS
        cm_urls = list(set(re.findall(r'https?://[^\s"\']+doubleclick[^\s"\']{0,150}', js)))
        dv_urls = list(set(re.findall(r'https?://[^\s"\']+doubleverify[^\s"\']{0,150}', js)))

        cm_ok = bool(cm_hits or cm_urls)
        dv_ok = bool(dv_hits or dv_urls)
        status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

        print(f"  CM360: {'✅' if cm_ok else '❌'} {cm_urls[0][:120] if cm_urls else (cm_hits[0] if cm_hits else '—')}")
        print(f"  DV:    {'✅' if dv_ok else '❌'} {dv_urls[0][:120] if dv_urls else (dv_hits[0] if dv_hits else '—')}")
        print(f"  → {status}")

        return {"label": "YOC_UVS", "site": "yoc.com", "fmt": "Universal Video",
                "slot": "R925-rHx6-5h6M",
                "cm360": cm_ok, "cm_url": cm_urls[0][:120] if cm_urls else "—",
                "dv": dv_ok, "dv_url": dv_urls[0][:120] if dv_urls else "—",
                "status": status}
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"label": "YOC_UVS", "site": "yoc.com", "fmt": "Universal Video",
                "slot": "R925-rHx6-5h6M", "cm360": False, "cm_url": str(e),
                "dv": False, "dv_url": "—", "status": "ERROR"}


def run():
    results = []

    # YOC — no browser needed
    results.append(check_yoc())

    with sync_playwright() as pw:
        if not os.path.exists(STATE_FILE):
            setup_cookie_state(pw)

        for label, site, fmt, slot_id, url in WP_ROWS:
            r = check_wp_placement(pw, label, site, fmt, slot_id, url)
            results.append(r)

    # Summary
    print("\n" + "=" * 90)
    print(f"{'Label':<20} {'Fmt':<12} {'Slot':<12} {'CM360':>6} {'DV':>6}  Status")
    print("-" * 90)
    for r in results:
        print(f"{r['label']:<20} {r['fmt']:<12} {r['slot']:<12} {'✅' if r['cm360'] else '❌':>6} {'✅' if r['dv'] else '❌':>6}  {r['status']}")

    out = r"./fuelclient_cafe_results.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write("Fuelclient cafe — CM360 + DoubleVerify tag verification\n\n")
        f.write(f"{'Label':<20} {'Fmt':<12} {'Slot':<12} CM360  DV     Status\n")
        f.write("-" * 70 + "\n")
        for r in results:
            f.write(f"{r['label']:<20} {r['fmt']:<12} {r['slot']:<12} {'OK' if r['cm360'] else 'MISS':<6} {'OK' if r['dv'] else 'MISS':<6} {r['status']}\n")
            if r['cm360']:
                f.write(f"  CM360: {r['cm_url']}\n")
            if r['dv']:
                f.write(f"  DV:    {r['dv_url']}\n")
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    run()
