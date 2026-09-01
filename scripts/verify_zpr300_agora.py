"""
BankClient Obligacje — ZPR 300x600 + Agora moto.pl tag verification
Checks Adform impression (adfserve bn=) + click tag (C/?bn=) per creative
"""
from playwright.sync_api import sync_playwright
import re, time, sys

URLS = [
    ("ZPR 300x600 Linia3",  False, {90000001}, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000222&creativeId=900000036570"),
    ("ZPR 300x600 Linia4",  False, {90000004}, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000222&creativeId=900000059205"),
    ("Agora moto.pl Linia3",False, {90000006}, "http://moto.pl?google_preview=PLACEHOLDER&iu=90000007&gdfp_req=1&lineItemId=9000000823&creativeId=900000092043"),
    ("Agora moto.pl Linia4",False, {90000010}, "http://moto.pl?google_preview=PLACEHOLDER&iu=90000007&gdfp_req=1&lineItemId=9000000823&creativeId=900000093819"),
]

log = open("zpr300_agora_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj wszystko',
                             'Akceptuj','Zgadzam się','Accept all','Accept',
                             'Zgoda','Rozumiem'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked:
            print(f"    [consent-js] '{clicked}'")
            return True
    except: pass
    for sel in ["[class*='accept']","#onetrust-accept-btn-handler","button.sp_choice_type_11",
                "[class*='agree']","[data-cy='accept-all']","[class*='accept-all']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click()
                print(f"    [consent-sel] {sel}")
                return True
        except: pass
    for frame in page.frames:
        if frame == page.main_frame: continue
        try:
            clicked = frame.evaluate("""() => {
                const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Zgadzam się','Accept all','Accept'];
                for (const b of document.querySelectorAll('button')) {
                    const t = b.innerText.trim();
                    if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
                }
                return null;
            }""")
            if clicked:
                print(f"    [consent-iframe] '{clicked}'")
                return True
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
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # Consent setup
    print("\n[=== Consent Setup ===]")
    for url in ["https://www.eska.pl/", "https://moto.pl/"]:
        page = desktop_ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.bring_to_front()
            time.sleep(8)
            if click_consent(page):
                time.sleep(2)
                print(f"  [consent-setup] done -- {url}")
            else:
                print(f"  [consent-setup] no popup -- {url}")
        except Exception as e:
            print(f"  [consent-setup] error: {e}")
        finally:
            page.close()

    results = []
    print("\n" + "="*60)
    print("ZPR 300x600 + Agora moto.pl -- Adform tag verification")
    print("="*60)

    for label, is_mobile, expected_bns, url in URLS:
        imp_bns = []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            t = time.time() - t_ref[0] if t_ref[0] else 0
            if 'adform.net' in u:
                m = re.search(r'bn=(\d+)', u)
                if m and ('adfserve' in u or '1x1inv' in u):
                    bn = int(m.group(1))
                    if bn not in imp_bns:
                        imp_bns.append(bn)
                        print(f"    [IMP] bn={bn}  t+{t:.1f}s")

        page = desktop_ctx.new_page()
        page.on("request", on_req)
        print(f"\n[{label}]")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
        except Exception as e:
            print(f"  [load error] {e}")
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

        clk_bns = get_click_bn_from_dom(page)
        for bn in sorted(clk_bns):
            print(f"    [DOM-CLK] bn={bn}")
        page.close()

        imp = list(set(imp_bns))
        clk = sorted(clk_bns)

        imp_ok = bool(set(imp) & expected_bns)
        clk_ok = bool(clk_bns & expected_bns)

        if imp_ok and clk_ok:
            status = "[PASS]"
        elif imp_ok:
            status = "[IMP OK / CLICK MISSING]"
        elif imp or clk:
            status = f"[FAIL - wrong bn: imp={imp} clk={clk}]"
        else:
            status = "[NO AD FIRED]"

        print(f"  Status   : {status}")
        print(f"  Expected : bn={sorted(expected_bns)}")
        print(f"  IMP bns  : {imp or 'none'}")
        print(f"  CLK bns  : {clk or 'none'}")
        results.append((label, sorted(expected_bns), status, imp, clk))

    browser.close()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for label, exp, status, imp, clk in results:
        print(f"  {status:<40} expected={exp}  {label}")

    passed = sum(1 for *_, s, i, c in results if s == "[PASS]")
    print(f"\n{passed}/{len(results)} fully verified (impression + click)")

log.close()
