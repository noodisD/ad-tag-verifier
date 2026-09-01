"""
Verify click tag bn= matches impression bn= for every eska.pl creative.
"""
from playwright.sync_api import sync_playwright
import re, time, sys

URLS = [
    ("Linia3 Screening desktop",       False, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000027674"),
    ("Linia3 Screening mobile top",    True,  "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000027641"),
    ("Linia3 Screening mobile bottom", True,  "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000027689"),
    ("Linia3 Floorad desktop",         False, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000396&creativeId=900000042591"),
    ("Linia3 Floorad mobile",          True,  "https://www.eska.pl/news/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000396&creativeId=900000050892"),
    ("Linia4 Screening desktop",       False, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000056451"),
    ("Linia4 Screening mobile top",    True,  "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000049077"),
    ("Linia4 Screening mobile bottom", True,  "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000049452"),
    ("Linia4 Floorad desktop",         False, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000396&creativeId=900000042567"),
    ("Linia4 Floorad mobile",          True,  "https://www.eska.pl/news/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000396&creativeId=900000042012"),
]

log = open("eska_click_all.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Zgadzam się'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked: return True
    except: pass
    return False

def get_click_bn_from_dom(page):
    """Find adform /C/?bn= in all frames (URL-encoded or plain)"""
    found_bns = set()
    for frame in page.frames:
        try:
            bns = frame.evaluate(r"""() => {
                const bns = new Set();
                const bnRe = /adform\.net\/C\/[^"'\s]*bn[=%]+(3D)?(\d+)/gi;
                // Check href and src attributes
                document.querySelectorAll('[href],[src]').forEach(el => {
                    ['href','src'].forEach(a => {
                        const v = el.getAttribute(a) || '';
                        const dec = decodeURIComponent(v);
                        const m = dec.match(/adform\.net\/C\/.*?bn=(\d+)/i);
                        if (m) bns.add(parseInt(m[1]));
                    });
                });
                // Check scripts
                document.querySelectorAll('script').forEach(s => {
                    const dec = decodeURIComponent(s.textContent);
                    const m = dec.match(/adform\.net\/C\/.*?bn=(\d+)/i);
                    if (m) bns.add(parseInt(m[1]));
                });
                return [...bns];
            }""")
            for bn in bns:
                found_bns.add(bn)
        except: pass
    return found_bns

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    desktop_ctx = browser.new_context(
        viewport={"width": 1280, "height": 900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    mobile_ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
    )

    # Consent setup
    for ctx, url in [(desktop_ctx, "https://www.eska.pl/"), (mobile_ctx, "https://www.eska.pl/?force_mobile=1")]:
        s = ctx.new_page()
        s.goto(url, wait_until="domcontentloaded", timeout=25000)
        s.bring_to_front(); time.sleep(8); click_consent(s); time.sleep(2); s.close()

    results = []
    print("\n" + "="*60)
    print("eska.pl — Impression vs Click bn= verification")
    print("="*60)

    for label, is_mobile, url in URLS:
        ctx = mobile_ctx if is_mobile else desktop_ctx
        imp_bns = []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            if 'adform.net' in u:
                m = re.search(r'bn=(\d+)', u)
                if m and ('adfserve' in u or '1x1inv' in u):
                    bn = int(m.group(1))
                    if bn not in imp_bns:
                        imp_bns.append(bn)

        page = ctx.new_page()
        page.on("request", on_req)
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        t_ref[0] = time.time()
        page.bring_to_front()
        click_consent(page)
        time.sleep(2)

        for _ in range(100):
            if imp_bns: time.sleep(2); break
            try: page.evaluate("window.scrollBy(0, 250)")
            except: pass
            time.sleep(1.2)
        time.sleep(2)

        click_bns = get_click_bn_from_dom(page)
        page.close()

        imp = list(set(imp_bns))
        clk = sorted(click_bns)

        # Check: each impression bn= has matching click bn=
        match = all(bn in click_bns for bn in imp) if imp else False
        status = "✅ MATCH" if match else ("❌ MISMATCH" if imp else "❌ NO AD")

        print(f"\n[{label}]")
        print(f"  IMP bn= : {imp or 'none'}")
        print(f"  CLK bn= : {clk or 'none'}")
        print(f"  Status  : {status}")
        results.append((label, imp, clk, status))

    browser.close()

    print("\n" + "="*60)
    print("SUMMARY — Impression/Click bn= match")
    print("="*60)
    for label, imp, clk, status in results:
        print(f"  {status}  imp={imp or 'none'}  clk={clk or 'none'}  {label}")

    ok = sum(1 for *_, s in results if "MATCH" in s)
    print(f"\n{ok}/{len(results)} creatives: impression bn= matches click bn=")

log.close()
