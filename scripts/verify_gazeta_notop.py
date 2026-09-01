"""
Gazeta.pl branding — stay at top, no scroll, wait 45s.
If branding is in article header it fires immediately on load.
Also check DOM for ALL bn= values in 88859xxx range.
"""
from playwright.sync_api import sync_playwright
import re, time, sys

BN_GAZETA = {90000001, 90000002, 90000003, 90000004, 90000005, 90000006, 90000007, 90000008, 90000009}

URLS = [
    ("D1 creativeId=900000107863", False, "https://next.gazeta.pl/next/7,151645,90000011,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001397&creativeId=900000107863"),
    ("D2 creativeId=900000107323", False, "https://next.gazeta.pl/next/7,151645,90000011,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001397&creativeId=900000107323"),
    ("D3 creativeId=900000106858", False, "https://next.gazeta.pl/next/7,151645,90000011,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001397&creativeId=900000106858"),
    ("M1 creativeId=900000107488", True,  "https://next.gazeta.pl/next/7,151645,90000011,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001397&creativeId=900000107488"),
    ("M2 creativeId=900000106660", True,  "https://next.gazeta.pl/next/7,151645,90000011,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001397&creativeId=900000106660"),
    ("M3 creativeId=900000149436", True,  "https://next.gazeta.pl/next/7,151645,90000011,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001397&creativeId=900000149436"),
]

log = open("gazeta_notop_results.txt", "w", encoding="utf-8", buffering=1)
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
        if clicked: print(f"    [consent] '{clicked}'"); return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler","[class*='accept']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); return True
        except: pass
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    desktop_ctx = browser.new_context(viewport={"width":1280,"height":900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    mobile_ctx  = browser.new_context(viewport={"width":390,"height":844}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36")

    # Consent warmup
    for ctx, url in [(desktop_ctx,"https://next.gazeta.pl/"),(mobile_ctx,"https://next.gazeta.pl/")]:
        pg = ctx.new_page()
        pg.goto(url,wait_until="domcontentloaded",timeout=25000)
        pg.bring_to_front(); time.sleep(8); click_consent(pg); time.sleep(2); pg.close()

    results = []
    print("\n" + "="*60)
    print("Gazeta.pl — no-scroll top-of-page test + deep DOM scan")
    print("="*60)

    for label, is_mobile, url in URLS:
        ctx = mobile_ctx if is_mobile else desktop_ctx
        fired_bns = []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            if 'adform' not in u.lower(): return
            m = re.search(r'bn=(\d+)', u)
            if not m: return
            bn = int(m.group(1))
            t = time.time() - t_ref[0]
            if bn not in fired_bns:
                fired_bns.append(bn)
                tag = " <-- MATCH" if bn in BN_GAZETA else ""
                print(f"    [t+{t:.0f}s bn={bn}]{tag}  {u[:90]}")

        page = ctx.new_page()
        page.on("request", on_req)
        print(f"\n[{label}]")
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        t_ref[0] = time.time()
        page.bring_to_front()
        click_consent(page)
        # NO SCROLL — stay at top for 45 seconds
        time.sleep(45)

        # Deep DOM scan of all frame HTML
        all_imp, all_clk = set(), set()
        for frame in page.frames:
            try:
                r = frame.evaluate(r"""() => {
                    const h = document.documentElement.outerHTML;
                    const imp=new Set(), clk=new Set();
                    const ri=/adfserve[^\s"'<>]*bn=(\d+)/gi;
                    const rc=/adform\.net\/C\/[^\s"'<>]*bn=(\d+)/gi;
                    let m;
                    while((m=ri.exec(h))!==null) imp.add(parseInt(m[1]));
                    while((m=rc.exec(h))!==null) clk.add(parseInt(m[1]));
                    return {imp:[...imp],clk:[...clk]};
                }""")
                for b in r['imp']: all_imp.add(b)
                for b in r['clk']: all_clk.add(b)
            except: pass

        imp_match = all_imp & BN_GAZETA
        clk_match = all_clk & BN_GAZETA
        net_match = set(b for b in fired_bns if b in BN_GAZETA)

        if imp_match: print(f"    [DOM-IMP] {sorted(imp_match)}")
        if clk_match: print(f"    [DOM-CLK] {sorted(clk_match)}")
        if not imp_match and not clk_match and not net_match:
            other = set(b for b in fired_bns if b not in BN_GAZETA)
            if other: print(f"    [other bn fired] {sorted(other)}")
            else: print(f"    [nothing fired]")

        page.close()

        imp_ok = bool(net_match or imp_match)
        clk_ok = bool(clk_match)
        if imp_ok and clk_ok:  status = "[PASS]"
        elif clk_ok:           status = "[CLK OK]"
        elif imp_ok:           status = "[IMP OK]"
        elif fired_bns:        status = "[WRONG BN]"
        else:                  status = "[NO TAG]"

        print(f"  >> {status}")
        results.append((label, status, sorted(net_match|imp_match), sorted(clk_match)))

    browser.close()
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for label, status, imp, clk in results:
        print(f"  {status:<12} imp={imp or 'none'}  clk={clk or 'none'}  {label}")

log.close()
