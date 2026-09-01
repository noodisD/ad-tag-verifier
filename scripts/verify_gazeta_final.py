"""
Gazeta.pl — final verification.
Shared context (with cookies), long wait, captures ALL Adform bn= values.
Separates: branding creative pixels (expected) vs article pixels (noise).
"""
from playwright.sync_api import sync_playwright
import re, time, sys

BN_GAZETA = {90000001, 90000002, 90000003, 90000004, 90000005, 90000006, 90000007, 90000008, 90000009}

URLS = [
    ("Gazeta desktop 1", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137863"),
    ("Gazeta desktop 2", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137323"),
    ("Gazeta desktop 3", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000136858"),
    ("Gazeta mobile 1",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137488"),
    ("Gazeta mobile 2",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000136660"),
    ("Gazeta mobile 3",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000149436"),
]

log = open("gazeta_final_results.txt", "w", encoding="utf-8", buffering=1)
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
        if clicked: print(f"    [consent-js] '{clicked}'"); return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler","[class*='accept']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); print(f"    [consent-sel] {sel}"); return True
        except: pass
    return False

def deep_dom_scan(page):
    """Scan every frame's full HTML source for any bn= in the 88859xxx range"""
    found_imp = set()
    found_clk = set()
    for frame in page.frames:
        try:
            res = frame.evaluate(r"""() => {
                const html = document.documentElement ? document.documentElement.outerHTML : '';
                const imp = new Set(), clk = new Set();
                const impRe = /adfserve[^\s"'<>]*bn=(\d+)/gi;
                const clkRe = /adform\.net\/C\/[^\s"'<>]*bn=(\d+)/gi;
                let m;
                while ((m = impRe.exec(html)) !== null) imp.add(parseInt(m[1]));
                while ((m = clkRe.exec(html)) !== null) clk.add(parseInt(m[1]));
                return { imp: [...imp], clk: [...clk] };
            }""")
            for b in res['imp']: found_imp.add(b)
            for b in res['clk']: found_clk.add(b)
        except: pass
    return found_imp, found_clk

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    desktop_ctx = browser.new_context(
        viewport={"width": 1280, "height": 900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    mobile_ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
    )

    # Consent setup — warm up the cookies so Adform pixels fire
    print("[=== Consent Setup ===]")
    for ctx, url in [(desktop_ctx, "https://next.gazeta.pl/"), (mobile_ctx, "https://next.gazeta.pl/")]:
        pg = ctx.new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=25000)
        pg.bring_to_front(); time.sleep(8); click_consent(pg); time.sleep(3)
        print(f"  done -- {url}"); pg.close()

    results = []
    print("\n" + "="*60)
    print("Gazeta.pl -- final verification (long wait + deep DOM scan)")
    print("="*60)

    for label, is_mobile, url in URLS:
        ctx = mobile_ctx if is_mobile else desktop_ctx
        imp_bns, clk_bns = [], []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            t = time.time() - t_ref[0] if t_ref[0] else 0
            if 'adform' not in u.lower(): return
            m = re.search(r'bn=(\d+)', u)
            if not m: return
            bn = int(m.group(1))
            if 'adfserve' in u or '1x1inv' in u:
                if bn not in imp_bns:
                    imp_bns.append(bn)
                    tag = " <-- TARGET!" if bn in BN_GAZETA else ""
                    print(f"    [IMP t+{t:.0f}s] bn={bn}{tag}")
            elif '/C/' in u:
                if bn not in clk_bns:
                    clk_bns.append(bn)
                    tag = " <-- TARGET!" if bn in BN_GAZETA else ""
                    print(f"    [CLK t+{t:.0f}s] bn={bn}{tag}")

        page = ctx.new_page()
        page.on("request", on_req)
        print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")

        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        t_ref[0] = time.time()
        page.bring_to_front()
        click_consent(page)
        time.sleep(3)

        # Slow scroll — 90 steps, gives content 2 min to fire
        for i in range(90):
            try: page.evaluate("window.scrollBy(0, 200)")
            except: pass
            time.sleep(1.3)

        time.sleep(5)

        # Deep DOM scan
        dom_imp, dom_clk = deep_dom_scan(page)
        imp_dom_match = dom_imp & BN_GAZETA
        clk_dom_match = dom_clk & BN_GAZETA
        if imp_dom_match: print(f"    [DOM-IMP match] bn={sorted(imp_dom_match)}")
        if clk_dom_match: print(f"    [DOM-CLK match] bn={sorted(clk_dom_match)}")

        page.close()

        imp_net  = [b for b in imp_bns if b in BN_GAZETA]
        clk_net  = [b for b in clk_bns if b in BN_GAZETA]
        imp_ok   = bool(imp_net or imp_dom_match)
        clk_ok   = bool(clk_net or clk_dom_match)

        if imp_ok and clk_ok:   status = "[PASS]"
        elif clk_ok:            status = "[CLK OK / IMP not captured]"
        elif imp_ok:            status = "[IMP OK / CLK not captured]"
        elif imp_bns or clk_bns:status = "[WRONG BN - other campaign]"
        else:                   status = "[NO TAG FIRED]"

        print(f"  Status : {status}")
        results.append((label, status, sorted(imp_net or imp_dom_match), sorted(clk_net or clk_dom_match)))

    browser.close()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for label, status, imp, clk in results:
        print(f"  {status:<38} {label}")
        if imp: print(f"      imp bn={imp}")
        if clk: print(f"      clk bn={clk}")
    passed = sum(1 for _,s,_,_ in results if s=="[PASS]")
    ok = sum(1 for _,s,_,_ in results if "OK" in s or s=="[PASS]")
    print(f"\n{passed}/{len(results)} fully verified | {ok}/{len(results)} at least one tag confirmed")

log.close()
