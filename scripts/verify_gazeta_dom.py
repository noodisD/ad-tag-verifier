"""
Gazeta.pl sponsored article branding — DOM scan for Adform bn= values.
Looks inside the GAM creative iframe for click tag (C/?bn=) and impression pixel (adfserve/?bn=).
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

log = open("gazeta_dom_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

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
    for sel in ["#onetrust-accept-btn-handler","[class*='accept']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click(); print(f"    [consent-sel] {sel}"); return True
        except: pass
    return False

def scan_all_bns(page):
    """Deep scan every frame and source for any Adform bn= values"""
    imp_bns = set()
    clk_bns = set()

    for frame in page.frames:
        try:
            result = frame.evaluate(r"""() => {
                const imp = new Set(), clk = new Set();
                const impRe = /adfserve[^"'\s]*bn=(\d+)/gi;
                const clkRe = /adform\.net\/C\/[^"'\s]*bn=(\d+)/gi;

                function scan(text) {
                    const d = decodeURIComponent(text || '');
                    let m;
                    while ((m = impRe.exec(d)) !== null) imp.add(parseInt(m[1]));
                    impRe.lastIndex = 0;
                    while ((m = clkRe.exec(d)) !== null) clk.add(parseInt(m[1]));
                    clkRe.lastIndex = 0;
                }

                // Scan all elements
                document.querySelectorAll('*').forEach(el => {
                    ['href','src','onclick','data-click','data-impression'].forEach(a => {
                        scan(el.getAttribute(a) || '');
                    });
                    scan(el.innerHTML || '');
                });
                // Scan scripts
                document.querySelectorAll('script').forEach(s => scan(s.textContent));
                // Scan all text nodes
                scan(document.body ? document.body.innerHTML : '');

                return { imp: [...imp], clk: [...clk] };
            }""")
            for bn in result['imp']: imp_bns.add(bn)
            for bn in result['clk']: clk_bns.add(bn)
        except: pass

    return imp_bns, clk_bns

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

    print("\n[=== Consent Setup ===]")
    for ctx, url in [(desktop_ctx, "https://next.gazeta.pl/"), (mobile_ctx, "https://next.gazeta.pl/")]:
        pg = ctx.new_page()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=25000)
            pg.bring_to_front(); time.sleep(8); click_consent(pg); time.sleep(2)
            print(f"  [consent-setup] done -- {url}")
        except Exception as e: print(f"  [consent-setup] error: {e}")
        finally: pg.close()

    results = []
    print("\n" + "="*60)
    print("Gazeta.pl -- DOM scan for Adform bn= in all frames")
    print("="*60)

    for label, is_mobile, url in URLS:
        # Fresh context per URL to avoid frequency cap
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844} if is_mobile else {"width": 1280, "height": 900},
            locale="pl-PL",
            user_agent=("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
                        if is_mobile else
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        )
        page = ctx.new_page()
        print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            print(f"  [load error] {e}")

        page.bring_to_front()
        click_consent(page)
        time.sleep(3)

        # Scroll to trigger lazy-loaded branding elements
        for _ in range(20):
            try: page.evaluate("window.scrollBy(0, 300)")
            except: pass
            time.sleep(0.5)

        time.sleep(5)  # wait for branding creative to fully render

        imp_bns, clk_bns = scan_all_bns(page)

        # Filter to only show Gazeta bn= values
        imp_match = imp_bns & BN_GAZETA
        clk_match = clk_bns & BN_GAZETA
        imp_other = imp_bns - BN_GAZETA
        clk_other = clk_bns - BN_GAZETA

        if imp_match: print(f"    [IMP-match] bn={sorted(imp_match)}")
        if clk_match: print(f"    [CLK-match] bn={sorted(clk_match)}")
        if imp_other: print(f"    [IMP-other] bn={sorted(imp_other)} (different campaign)")
        if clk_other: print(f"    [CLK-other] bn={sorted(clk_other)} (different campaign)")

        page.close()
        ctx.close()

        imp_ok = bool(imp_match)
        clk_ok = bool(clk_match)

        if imp_ok and clk_ok:
            status = "[PASS]"
        elif clk_ok:
            status = "[CLK OK / IMP not in DOM]"
        elif imp_ok:
            status = "[IMP OK / CLK not in DOM]"
        elif imp_bns or clk_bns:
            status = "[FAIL - wrong bn (other campaign)]"
        else:
            status = "[NO ADFORM TAGS FOUND]"

        print(f"  Status : {status}")
        results.append((label, status, sorted(imp_match), sorted(clk_match)))

    browser.close()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for label, status, imp, clk in results:
        print(f"  {status:<35} {label}")
        if imp: print(f"    imp bn={imp}")
        if clk: print(f"    clk bn={clk}")

    passed = sum(1 for _, s, _, _ in results if s == "[PASS]")
    clk_ok_count = sum(1 for _, s, _, _ in results if "CLK OK" in s or s == "[PASS]")
    print(f"\n{passed}/{len(results)} fully verified  |  {clk_ok_count}/{len(results)} click tags found in DOM")

log.close()
