"""Diagnostic: capture ALL adform.net requests on Agora moto.pl to find impression endpoint"""
from playwright.sync_api import sync_playwright
import re, time, sys

log = open("diag_agora.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

URLS = [
    ("Agora Linia3", {90000001}, "http://moto.pl?google_preview=PLACEHOLDER&iu=90000002&gdfp_req=1&lineItemId=9000000323&creativeId=900000042043"),
    ("Agora Linia4", {90000005}, "http://moto.pl?google_preview=PLACEHOLDER&iu=90000002&gdfp_req=1&lineItemId=9000000323&creativeId=900000043819"),
]

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Zgadzam się','Accept all'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked: print(f"    [consent-js] '{clicked}'"); return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler","[class*='accept']","button.sp_choice_type_11"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click(); print(f"    [consent-sel] {sel}"); return True
        except: pass
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # Consent setup
    setup = ctx.new_page()
    setup.goto("https://moto.pl/", wait_until="domcontentloaded", timeout=25000)
    setup.bring_to_front(); time.sleep(8); click_consent(setup); time.sleep(2); setup.close()

    for label, expected_bns, url in URLS:
        all_adform = []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            t = time.time() - t_ref[0] if t_ref[0] else 0
            if 'adform' in u.lower():
                all_adform.append((t, u))
                print(f"    [ADFORM t+{t:.1f}s] {u[:180]}")

        page = ctx.new_page()
        page.on("request", on_req)
        print(f"\n{'='*60}\n[{label}]\n")
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        t_ref[0] = time.time()
        page.bring_to_front()
        click_consent(page)
        time.sleep(2)

        for _ in range(80):
            try: page.evaluate("window.scrollBy(0, 300)")
            except: pass
            time.sleep(1.2)

        time.sleep(3)
        page.close()

        print(f"\n  Total Adform requests: {len(all_adform)}")
        bns_seen = set()
        for t, u in all_adform:
            m = re.search(r'bn=(\d+)', u)
            if m: bns_seen.add(int(m.group(1)))
        print(f"  bn= values seen: {sorted(bns_seen)}")
        print(f"  Expected: {sorted(expected_bns)}")
        print(f"  Match: {bool(bns_seen & expected_bns)}")

    browser.close()
