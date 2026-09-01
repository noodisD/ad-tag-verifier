"""
Diagnostic: capture ALL network requests on one Gazeta.pl branded article URL.
Prints everything that fires — helps identify where the Adform branding pixel is.
"""
from playwright.sync_api import sync_playwright
import re, time, sys

URL = "https://next.gazeta.pl/next/7,151645,90000001,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000002&gdfp_req=1&lineItemId=9000000397&creativeId=900000047863"
BN_TARGET = {90000005, 90000006, 90000007, 90000008, 90000009, 90000010, 90000011, 90000012, 90000013}

log = open("diag_gazeta_one.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked: print(f"  [consent-js] '{clicked}'"); return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler","[class*='accept']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=1000):
                page.locator(sel).first.click(); print(f"  [consent-sel] {sel}"); return True
        except: pass
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    t_start = [0.0]
    all_requests = []

    def on_req(req):
        t = time.time() - t_start[0] if t_start[0] else 0
        u = req.url
        all_requests.append((t, u))
        # Print anything Adform-related immediately
        if 'adform' in u.lower():
            bn_m = re.search(r'bn=(\d+)', u)
            bn = int(bn_m.group(1)) if bn_m else None
            marker = " <-- TARGET!" if bn and bn in BN_TARGET else ""
            print(f"  [t+{t:.1f}s] ADFORM bn={bn}  {u[:120]}{marker}")

    page = ctx.new_page()
    page.on("request", on_req)

    print(f"Loading: {URL[:80]}...\n")
    page.goto(URL, wait_until="domcontentloaded", timeout=35000)
    t_start[0] = time.time()
    page.bring_to_front()
    time.sleep(3)
    click_consent(page)
    time.sleep(3)

    print("\n--- Scrolling ---")
    for i in range(30):
        try: page.evaluate("window.scrollBy(0, 300)")
        except: pass
        time.sleep(0.5)

    time.sleep(5)

    # Deep DOM scan across all frames
    print("\n--- DOM scan (all frames) ---")
    for frame in page.frames:
        try:
            found = frame.evaluate(r"""() => {
                const hits = [];
                const text = document.body ? document.body.innerHTML : '';
                const re = /bn=(\d+)/g;
                let m;
                while ((m = re.exec(text)) !== null) {
                    const bn = parseInt(m[1]);
                    if (bn > 90000014 && bn < 90000015) hits.push(bn);
                }
                return [...new Set(hits)];
            }""")
            if found:
                print(f"  Frame [{frame.url[:60]}]: bn= {found}")
        except: pass

    browser.close()

    print(f"\n--- Summary ---")
    print(f"Total requests: {len(all_requests)}")
    adform_bns = set()
    for t, u in all_requests:
        if 'adform' in u.lower():
            m = re.search(r'bn=(\d+)', u)
            if m: adform_bns.add(int(m.group(1)))
    print(f"All Adform bn= seen: {sorted(adform_bns)}")
    print(f"Target bn= matched: {sorted(adform_bns & BN_TARGET)}")

log.close()
