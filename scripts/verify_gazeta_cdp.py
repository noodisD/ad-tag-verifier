"""
Gazeta.pl sponsored article branding — CDP-level network capture.
Uses Chrome DevTools Protocol to intercept ALL requests including safeframe/cross-origin.
"""
from playwright.sync_api import sync_playwright
import re, time, sys, json

BN_GAZETA = {90000001, 90000002, 90000003, 90000004, 90000005, 90000006, 90000007, 90000008, 90000009}

URLS = [
    ("Gazeta desktop 1", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137863"),
    ("Gazeta desktop 2", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137323"),
    ("Gazeta desktop 3", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000136858"),
    ("Gazeta mobile 1",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137488"),
    ("Gazeta mobile 2",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000136660"),
    ("Gazeta mobile 3",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000149436"),
]

log = open("gazeta_cdp_results.txt", "w", encoding="utf-8", buffering=1)
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

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    print("\n" + "="*60)
    print("Gazeta.pl -- CDP network capture (all frames/safeframes)")
    print("="*60)

    for label, is_mobile, url in URLS:
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844} if is_mobile else {"width": 1280, "height": 900},
            locale="pl-PL",
            user_agent=("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
                        if is_mobile else
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        )
        page = ctx.new_page()

        # CDP session — captures ALL network requests at browser level
        client = ctx.new_cdp_session(page)
        client.send("Network.enable")

        imp_bns = []
        clk_bns = []
        t_ref = [time.time()]

        def on_cdp_request(params):
            req = params.get("request", {})
            u = req.get("url", "")
            t = time.time() - t_ref[0]
            if "adform" not in u.lower(): return
            m = re.search(r"bn=(\d+)", u)
            bn = int(m.group(1)) if m else None
            if not bn: return
            if "adfserve" in u or "1x1inv" in u:
                if bn not in imp_bns:
                    imp_bns.append(bn)
                    marker = " <-- MATCH!" if bn in BN_GAZETA else ""
                    print(f"    [IMP t+{t:.1f}s] bn={bn}{marker}")
            elif "/C/" in u:
                if bn not in clk_bns:
                    clk_bns.append(bn)
                    marker = " <-- MATCH!" if bn in BN_GAZETA else ""
                    print(f"    [CLK t+{t:.1f}s] bn={bn}{marker}")

        client.on("Network.requestWillBeSent", on_cdp_request)

        print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            print(f"  [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3)
        click_consent(page)
        time.sleep(3)

        # Scroll
        for _ in range(30):
            try: page.evaluate("window.scrollBy(0, 300)")
            except: pass
            time.sleep(0.5)
        time.sleep(5)

        imp_match = [b for b in imp_bns if b in BN_GAZETA]
        clk_match = [b for b in clk_bns if b in BN_GAZETA]

        if imp_match and clk_match:
            status = "[PASS]"
        elif clk_match:
            status = "[CLK OK / IMP not captured]"
        elif imp_match:
            status = "[IMP OK / CLK not captured]"
        elif imp_bns or clk_bns:
            status = "[WRONG BN]"
        else:
            status = "[NO TAG FIRED]"

        print(f"  Status : {status}")
        print(f"  IMP    : {imp_match or imp_bns or 'none'}")
        print(f"  CLK    : {clk_match or clk_bns or 'none'}")
        results.append((label, status, imp_match, clk_match))

        client.detach()
        page.close()
        ctx.close()

    browser.close()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for label, status, imp, clk in results:
        print(f"  {status:<35} {label}")
        if imp: print(f"    imp bn={imp}")
        if clk: print(f"    clk bn={clk}")

    passed = sum(1 for _, s, _, _ in results if s == "[PASS]")
    ok = sum(1 for _, s, _, _ in results if "OK" in s or s == "[PASS]")
    print(f"\n{passed}/{len(results)} fully verified  |  {ok}/{len(results)} at least one tag confirmed")

log.close()
