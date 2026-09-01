"""
BankClient Cyberbezpieczenstwo — Gazeta.pl sponsored article branding
6 test URLs (3 desktop + 3 mobile), Adform tags
"""
from playwright.sync_api import sync_playwright
import re, time, sys

# All valid Gazeta.pl bn= values from xlsx rows 44-52
BN_GAZETA = {90000001, 90000002, 90000003, 90000004, 90000005, 90000006, 90000007, 90000008, 90000009}

URLS = [
    ("Gazeta desktop 1", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137863"),
    ("Gazeta desktop 2", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137323"),
    ("Gazeta desktop 3", False, "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000136858"),
    ("Gazeta mobile 1",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000137488"),
    ("Gazeta mobile 2",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000136660"),
    ("Gazeta mobile 3",  True,  "https://next.gazeta.pl/next/7,151645,90000010,falszywa-reklama-jak-poznac-ze-to-oszustwo.html?google_preview=PLACEHOLDER&iu=90000011&gdfp_req=1&lineItemId=9000001297&creativeId=900000149436"),
]

log = open("gazeta_cyber_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Zgadzam się','Accept all','Accept'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked: print(f"    [consent-js] '{clicked}'"); return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler","[class*='accept']","button.sp_choice_type_11","[class*='agree']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click(); print(f"    [consent-sel] {sel}"); return True
        except: pass
    for frame in page.frames:
        if frame == page.main_frame: continue
        try:
            clicked = frame.evaluate("""() => {
                const phrases = ['Akceptuję','Akceptuj','Zgadzam się','Accept all','Accept'];
                for (const b of document.querySelectorAll('button')) {
                    const t = b.innerText.trim();
                    if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
                }
                return null;
            }""")
            if clicked: print(f"    [consent-iframe] '{clicked}'"); return True
        except: pass
    return False

def get_click_bn_from_dom(page):
    found = set()
    for frame in page.frames:
        try:
            bns = frame.evaluate(r"""() => {
                const bns = new Set();
                document.querySelectorAll('[href],[src],[onclick]').forEach(el => {
                    ['href','src','onclick'].forEach(a => {
                        const v = decodeURIComponent(el.getAttribute(a) || '');
                        const m = v.match(/adform\.net\/C\/.*?bn=(\d+)/i);
                        if (m) bns.add(parseInt(m[1]));
                    });
                });
                document.querySelectorAll('a').forEach(a => {
                    const h = decodeURIComponent(a.href || '');
                    const m = h.match(/adform\.net\/C\/.*?bn=(\d+)/i);
                    if (m) bns.add(parseInt(m[1]));
                });
                document.querySelectorAll('script').forEach(s => {
                    const ms = s.textContent.matchAll(/adform\.net\/C\/[^"'\s]*bn=(\d+)/gi);
                    for (const m of ms) bns.add(parseInt(m[1]));
                });
                return [...bns];
            }""")
            for bn in bns: found.add(bn)
        except: pass
    return found

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
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.bring_to_front(); time.sleep(8)
            if click_consent(page): time.sleep(2); print(f"  [consent-setup] done -- {url}")
            else: print(f"  [consent-setup] no popup -- {url}")
        except Exception as e: print(f"  [consent-setup] error: {e}")
        finally: page.close()

    results = []
    print("\n" + "="*60)
    print("Gazeta.pl Cyberbezpieczenstwo -- Adform tag verification")
    print("="*60)

    for label, is_mobile, url in URLS:
        ctx = mobile_ctx if is_mobile else desktop_ctx
        imp_bns = []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            t = time.time() - t_ref[0] if t_ref[0] else 0
            if 'adform' in u.lower():
                m = re.search(r'bn=(\d+)', u)
                if m and ('adfserve' in u or '1x1inv' in u):
                    bn = int(m.group(1))
                    if bn not in imp_bns:
                        imp_bns.append(bn)
                        print(f"    [IMP] bn={bn}  t+{t:.1f}s")

        page = ctx.new_page()
        page.on("request", on_req)
        print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            print(f"  [load error] {e}")
        t_ref[0] = time.time()
        page.bring_to_front()
        click_consent(page)
        time.sleep(2)

        for _ in range(80):
            if imp_bns: time.sleep(2); break
            try: page.evaluate("window.scrollBy(0, 250)")
            except: pass
            time.sleep(1.2)
        time.sleep(2)

        clk_bns = get_click_bn_from_dom(page)
        for bn in sorted(clk_bns):
            print(f"    [DOM-CLK] bn={bn}")
        page.close()

        imp = list(set(imp_bns))
        clk = sorted(clk_bns)
        imp_ok = bool(set(imp) & BN_GAZETA)
        clk_ok = bool(clk_bns & BN_GAZETA)

        if imp_ok and clk_ok:
            status = "[PASS]"
        elif clk_ok:
            status = "[CLK OK / IMP not captured]"
        elif imp_ok:
            status = "[IMP OK / CLK MISSING]"
        elif imp or clk:
            status = f"[FAIL - wrong bn]"
        else:
            status = "[NO AD FIRED]"

        print(f"  Status : {status}")
        print(f"  IMP bns: {imp or 'none'}")
        print(f"  CLK bns: {clk or 'none'}")
        results.append((label, status, imp, clk))

    browser.close()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for label, status, imp, clk in results:
        print(f"  {status:<35} {label}")
    passed = sum(1 for _, s, _, _ in results if s == "[PASS]")
    clk_ok = sum(1 for _, s, _, _ in results if "CLK OK" in s or s == "[PASS]")
    print(f"\n{passed}/{len(results)} fully verified  |  {clk_ok}/{len(results)} click tags confirmed")

log.close()
