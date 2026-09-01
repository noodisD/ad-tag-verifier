"""
Fuelclient — deep verification for 3 slots where CM360 was not detected.
- Screenshots to confirm ad rendered
- Checks iframe src + HTML content for embedded CM360 tags
- Longer wait (40s)
- Scrolls page to trigger lazy-load ads
"""

import re, time, os, base64
from playwright.sync_api import sync_playwright

STATE_FILE = r"./session_state.json"
SHOT_DIR   = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

CM360_PATTERNS = [
    'ad.doubleclick.net/ddm/trackimp',
    'ad.doubleclick.net/ddm/trackclk',
    'ad.doubleclick.net/ddm/jump',
    'ad.doubleclick.net/ddm/clk',
    'ad.doubleclick.net/ddm/kimpj',
    'ad.doubleclick.net/ddm/kclk',
    'googleads.g.doubleclick.net',
    'doubleclick.net',
]
DV_PATTERNS = ['pub.doubleverify.com','cdn.doubleverify.com','tps.doubleverify.com']

def has_cm360(text): return any(p in text for p in CM360_PATTERNS)
def has_dv(text):    return any(p in text for p in DV_PATTERNS)

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

SLOTS = [
    ("CB_desktop",    "1725483",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=desktop_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725483%22%7D%5D&testPos=2",
     {"width": 1280, "height": 800}, "desktop"),

    ("CB_mobile",     "1725484",
     "https://wiadomosci.wp.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=mobile_comm&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner_Commercial_Break%2F1725484%22%7D%5D&testPos=2",
     {"width": 390, "height": 844}, "mobile"),

    ("300x600_desktop","1725498",
     "https://www.pudelek.pl/?wfName=281478_3087096_Fuelclient cafe_MegaReach_mix_RM+_01&creName=300_600_desktop&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22208526%2F1494741%2Fiaq%2FBaner%2F1725498%22%7D%5D&testPos=36",
     {"width": 1280, "height": 800}, "desktop"),
]

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
UA_MOBILE  = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36"


def check_deep(pw, label, slot_id, url, viewport, vp_type):
    ua = UA_MOBILE if vp_type == "mobile" else UA_DESKTOP
    net_cm360, net_dv = [], []
    all_requests = []

    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        storage_state=STATE_FILE, viewport=viewport,
        user_agent=ua, locale="pl-PL",
        is_mobile=(vp_type == "mobile"),
        has_touch=(vp_type == "mobile"))

    def on_req(req):
        u = req.url
        all_requests.append(u)
        if has_cm360(u) and u not in net_cm360: net_cm360.append(u)
        if has_dv(u)    and u not in net_dv:    net_dv.append(u)

    page = ctx.new_page()
    page.on("request", on_req)
    ctx.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [WARN goto] {e}")

    time.sleep(3)
    accept_cookies(page)
    time.sleep(5)

    # Scroll down to trigger lazy-load ads
    for _ in range(6):
        page.keyboard.press("PageDown")
        time.sleep(1)

    time.sleep(15)  # give ads time to fire

    # Screenshot
    shot_path = os.path.join(SHOT_DIR, f"{label}.png")
    try:
        page.screenshot(path=shot_path, full_page=False)
        print(f"  [screenshot] {shot_path}")
    except Exception as e:
        print(f"  [screenshot ERR] {e}")

    # Check all iframes for embedded CM360 in src or content
    iframe_cm360 = []
    iframe_dv    = []
    for frame in page.frames:
        frame_url = frame.url or ""
        if has_cm360(frame_url): iframe_cm360.append(f"frame_src: {frame_url[:130]}")
        if has_dv(frame_url):    iframe_dv.append(f"frame_src: {frame_url[:130]}")
        try:
            html = frame.content()
            if has_cm360(html):
                hits = re.findall(r'["\']([^"\']*doubleclick\.net[^"\']{0,150})["\']', html)
                for h in hits[:3]: iframe_cm360.append(f"frame_html: {h[:130]}")
            if has_dv(html):
                hits = re.findall(r'["\']([^"\']*doubleverify\.com[^"\']{0,120})["\']', html)
                for h in hits[:3]: iframe_dv.append(f"frame_html: {h[:130]}")
        except Exception:
            pass

    ctx.close(); browser.close()

    cm_net = bool(net_cm360)
    cm_ifr = bool(iframe_cm360)
    dv_net = bool(net_dv)
    dv_ifr = bool(iframe_dv)
    cm_ok  = cm_net or cm_ifr
    dv_ok  = dv_net or dv_ifr

    status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))

    print(f"\n{'='*70}")
    print(f"[{label}]  slot={slot_id}  viewport={vp_type}")
    print(f"  CM360 network ({len(net_cm360)}):  {net_cm360[0][:130] if net_cm360 else '—'}")
    print(f"  CM360 iframe  ({len(iframe_cm360)}):  {iframe_cm360[0][:130] if iframe_cm360 else '—'}")
    print(f"  DV    network ({len(net_dv)}):  {net_dv[0][:130] if net_dv else '—'}")
    print(f"  DV    iframe  ({len(iframe_dv)}):  {iframe_dv[0][:130] if iframe_dv else '—'}")
    print(f"  Total requests: {len(all_requests)}")
    print(f"  → CM360: {'✅' if cm_ok else '❌'}  DV: {'✅' if dv_ok else '❌'}  STATUS: {status}")

    return {"label": label, "slot": slot_id, "vp": vp_type,
            "cm360": cm_ok, "dv": dv_ok, "status": status,
            "cm_net": net_cm360, "cm_ifr": iframe_cm360,
            "dv_net": net_dv, "dv_ifr": iframe_dv}


def run():
    results = []
    with sync_playwright() as pw:
        for label, slot_id, url, viewport, vp_type in SLOTS:
            r = check_deep(pw, label, slot_id, url, viewport, vp_type)
            results.append(r)

    print(f"\n{'='*70}")
    print("PODSUMOWANIE")
    print(f"{'Label':<20} {'Slot':<10} {'CM360':>6} {'DV':>6}  Status")
    print("-"*60)
    for r in results:
        print(f"{r['label']:<20} {r['slot']:<10} {'✅' if r['cm360'] else '❌':>6} {'✅' if r['dv'] else '❌':>6}  {r['status']}")

if __name__ == "__main__":
    run()
