"""
Fuelclient — PushAd (6 push previews) + Agora/Gazeta.pl (2 display banners)
CM360 + DoubleVerify tag check
"""
import re, time, os
from playwright.sync_api import sync_playwright

SHOT_DIR = r"./screenshots"
os.makedirs(SHOT_DIR, exist_ok=True)

CM360_DDM  = 'ad.doubleclick.net/ddm/'
DV_PATTERN = 'doubleverify.com'

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
UA_MOBILE  = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36"

PLACEMENTS = [
    # PushAd
    ("PushAd_kawa_wiz_desktop", "push", {"width":1280,"height":800}, UA_DESKTOP, False,
     "https://app2.push-ad.com/preview/2085eb90000001bf4e59375f478875e66a4720f4e05d4f6e12a1122f02d27533"),
    ("PushAd_kawa_wiz_mobile",  "push", {"width":390,"height":844},  UA_MOBILE,  True,
     "https://app2.push-ad.com/preview/9000000231eef4654ec002b4bc77fb6afe405e20d82f92306f7cabbbac2a5797"),
    ("PushAd_kawa_desktop",     "push", {"width":1280,"height":800}, UA_DESKTOP, False,
     "https://app2.push-ad.com/preview/22bc6c33c9cf9000000320f85e711387a05f41158e5cb5741212f82f47e3ad24"),
    ("PushAd_kawa_mobile",      "push", {"width":390,"height":844},  UA_MOBILE,  True,
     "https://app2.push-ad.com/preview/ba9a9acc3704663da63f5e290d34e9000000467fa8218edbcf1b0a9ff1ac621d"),
    ("PushAd_hotdog_desktop",   "push", {"width":1280,"height":800}, UA_DESKTOP, False,
     "https://app2.push-ad.com/preview/7f74d22e5af004c12553d2c637c7fc731ad65644b42a67903d8c1f876eed9850"),
    ("PushAd_hotdog_mobile",    "push", {"width":390,"height":844},  UA_MOBILE,  True,
     "https://app2.push-ad.com/preview/227bf4fed65589d15c87c0d382fe644b6428ec39032a115837c931ae89871fcf"),
    # Agora / Gazeta.pl
    ("Agora_GazetaHP_desktop",  "display", {"width":1280,"height":800}, UA_DESKTOP, False,
     "https://www.gazeta.pl/0,0.html?google_preview=PLACEHOLDER&iu=90000005&gdfp_req=1&lineItemId=9000000601&creativeId=900000075240"),
    ("Agora_GazetaHP_mobile",   "display", {"width":390,"height":844},  UA_MOBILE,  True,
     "https://www.gazeta.pl/0,0.html?google_preview=PLACEHOLDER&iu=90000005&gdfp_req=1&lineItemId=9000000601&creativeId=900000075282"),
]

def check(pw, label, fmt, viewport, ua, mobile, url):
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

    wait = 10 if fmt == "push" else 15
    time.sleep(wait)

    # Scan iframe HTML for embedded tags
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

    # For push: DV not applicable
    if fmt == "push":
        status = "PASS" if cm_ok else "FAIL"
        dv_note = "n/a (push)"
    else:
        status = "PASS" if (cm_ok and dv_ok) else ("CM_ONLY" if cm_ok else ("DV_ONLY" if dv_ok else "FAIL"))
        dv_note = dv_found[0][:100] if dv_found else "—"

    print(f"  CM360: {'✅' if cm_ok else '❌'}  {cm_found[0][:110] if cm_found else '—'}")
    print(f"  DV:    {'✅' if dv_ok else ('n/a' if fmt=='push' else '❌')}  {dv_note}")
    print(f"  → {status}")

    return {"label": label, "fmt": fmt, "cm360": cm_ok, "dv": dv_ok,
            "status": status, "cm_urls": cm_found, "dv_urls": dv_found}

def run():
    results = []
    with sync_playwright() as pw:
        for label, fmt, vp, ua, mob, url in PLACEMENTS:
            results.append(check(pw, label, fmt, vp, ua, mob, url))

    print(f"\n{'='*75}")
    print(f"{'Label':<30} {'Fmt':<8} CM360  DV      Status")
    print("-"*75)
    for r in results:
        dv_str = "✅" if r["dv"] else ("n/a" if r["fmt"]=="push" else "❌")
        print(f"{r['label']:<30} {r['fmt']:<8} {'✅' if r['cm360'] else '❌'}      {dv_str:<6}  {r['status']}")

if __name__ == "__main__":
    run()
