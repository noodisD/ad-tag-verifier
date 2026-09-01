"""
Adform tag verification — eska.pl (ZPR Media)
BankClient Obligacje campaign — Linia3 & Linia4
Source: zpr_21804_THE BANKING CLIENT_Obligacje_2026-05-18_2026-09-30_2026-06-01.xlsx
"""

from playwright.sync_api import sync_playwright
import re, time, sys

# All valid bn= for each Linia (any of these is a correct tag)
BN_LINIA3 = {90000001, 90000002, 90000003, 90000004, 90000005, 90000006, 90000007}
BN_LINIA4 = {90000008, 90000009, 90000010, 90000011, 90000012, 90000013, 90000014}

ESKA_URLS = [
    # Linia 3
    ("Linia3 Screening desktop",       False, BN_LINIA3, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001525&creativeId=900000167674"),
    ("Linia3 Screening mobile top",    True,  BN_LINIA3, "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001525&creativeId=900000167641"),
    ("Linia3 Screening mobile bottom", True,  BN_LINIA3, "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001525&creativeId=900000167689"),
    ("Linia3 Floorad desktop",         False, BN_LINIA3, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001796&creativeId=900000182591"),
    ("Linia3 Floorad mobile",          True,  BN_LINIA3, "https://www.eska.pl/news/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001796&creativeId=900000190892"),
    # Linia 4
    ("Linia4 Screening desktop",       False, BN_LINIA4, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001525&creativeId=900000196451"),
    ("Linia4 Screening mobile top",    True,  BN_LINIA4, "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001525&creativeId=900000189077"),
    ("Linia4 Screening mobile bottom", True,  BN_LINIA4, "https://www.eska.pl/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001525&creativeId=900000189452"),
    ("Linia4 Floorad desktop",         False, BN_LINIA4, "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001796&creativeId=900000182567"),
    ("Linia4 Floorad mobile",          True,  BN_LINIA4, "https://www.eska.pl/news/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000001796&creativeId=900000182012"),
]

ABT_EXPECTED = {"900000202"}

CONSENT_SELECTORS = [
    # eska.pl / ZPR CMP — button text is exactly "Akceptuję"
    "button:has-text('Akceptuję')",
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj wszystko')",
    "button:has-text('Akceptuj')",
    "button:has-text('Zgadzam się')", "button:has-text('Accept all')",
    "#onetrust-accept-btn-handler", ".js-accept-all", "[class*='accept-all']",
    "button[data-cy='accept-all']", "[class*='agree']", "[class*='accept']",
    "button.sp_choice_type_11",
]

def extract_bn(url):
    m = re.search(r'bn=(\d+)', url)
    return int(m.group(1)) if m else None

def extract_abt_order(url):
    m = re.search(r'o=(\d+)', url)
    return m.group(1) if m else None

def click_consent(page, ms=1500):
    # First try JS click on any button whose text matches Polish/English accept phrases
    # This avoids the slow per-selector timeout loop
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj wszystko',
                             'Akceptuj','Zgadzam się','Accept all','Accept'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) {
                    b.click();
                    return t;
                }
            }
            return null;
        }""")
        if clicked:
            print(f"    [consent-js] '{clicked}'")
            return True
    except: pass

    # Fallback: Playwright locators with short per-selector timeout
    for sel in CONSENT_SELECTORS:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click()
                print(f"    [consent] {sel}")
                return True
        except: pass

    # Iframe fallback
    for frame in page.frames:
        if frame == page.main_frame: continue
        try:
            clicked = frame.evaluate("""() => {
                const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj wszystko',
                                 'Akceptuj','Zgadzam się','Accept all'];
                for (const b of document.querySelectorAll('button')) {
                    const t = b.innerText.trim();
                    if (phrases.some(p => t === p || t.startsWith(p))) {
                        b.click(); return t;
                    }
                }
                return null;
            }""")
            if clicked:
                print(f"    [consent-iframe-js] '{clicked}'")
                return True
        except: pass
        for sel in CONSENT_SELECTORS:
            try:
                if frame.locator(sel).first.is_visible(timeout=400):
                    frame.locator(sel).first.click()
                    print(f"    [consent-iframe] {sel}")
                    return True
            except: pass
    return False

def setup_consent(ctx, url):
    page = ctx.new_page()
    try:
        print(f"  [consent-setup] {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.bring_to_front()
        time.sleep(8)
        if click_consent(page, ms=6000):
            time.sleep(2)
            print("  [consent-setup] done")
        else:
            print("  [consent-setup] no popup found")
    except Exception as e:
        print(f"  [consent-setup] error: {e}")
    finally:
        page.close()

def check_url(ctx, label, valid_bns, url):
    impression_bns = []
    click_bns = []
    abt_orders = []
    t_ref = [0.0]

    def on_req(req):
        u = req.url
        t = time.time() - t_ref[0] if t_ref[0] else 0
        if 'adform.net' in u:
            bn = extract_bn(u)
            if bn:
                if 'adfserve' in u or '1x1inv' in u:
                    if bn not in impression_bns:
                        impression_bns.append(bn)
                        print(f"    [IMP] bn={bn}  t+{t:.1f}s")
                elif '/C/' in u:
                    if bn not in click_bns:
                        click_bns.append(bn)
                        print(f"    [CLK-net] bn={bn}  t+{t:.1f}s")
        if 'abtshield.com' in u:
            order = extract_abt_order(u)
            if order and order not in abt_orders:
                abt_orders.append(order)
                print(f"    [ABT] o={order}  t+{t:.1f}s")

    page = ctx.new_page()
    page.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [load error] {e}")

    t_ref[0] = time.time()
    page.bring_to_front()

    if click_consent(page, ms=4000):
        try: page.wait_for_load_state("domcontentloaded", timeout=8000)
        except: pass
        t_ref[0] = time.time()
        impression_bns.clear()
        click_bns.clear()
        abt_orders.clear()

    time.sleep(1.5)

    for _ in range(100):
        if impression_bns:
            time.sleep(1.5)
            break
        try:
            page_h = page.evaluate("document.body.scrollHeight") or 20000
            cur = page.evaluate("window.pageYOffset + document.documentElement.clientHeight") or 0
            if cur >= page_h:
                break
            page.evaluate("window.scrollBy(0, 250)")
        except: pass
        time.sleep(1.2)

    time.sleep(2)

    for frame in page.frames:
        try:
            links = frame.evaluate("""(() => {
                const h = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    if (a.href.includes('adform')) h.push(a.href);
                });
                return h;
            })()""")
            for link in links:
                bn = extract_bn(link)
                if bn and bn not in click_bns:
                    click_bns.append(bn)
                    print(f"    [DOM-CLK] bn={bn}")
        except: pass

    page.close()

    imp_unique = list(set(impression_bns))
    clk_unique = list(set(click_bns))
    abt_unique = set(abt_orders)

    imp_ok = bool(imp_unique and (set(imp_unique) & valid_bns))
    clk_ok = bool(clk_unique and (set(clk_unique) & valid_bns))
    abt_ok = ABT_EXPECTED.issubset(abt_unique)

    if imp_ok and clk_ok:
        adform_status = "[PASS]"
    elif imp_ok:
        adform_status = "[IMP OK / CLICK MISSING]"
    elif imp_unique or clk_unique:
        adform_status = "[FAIL - wrong bn]"
    else:
        adform_status = "[NO AD FIRED]"

    abt_status = "[ABT OK]" if abt_ok else (f"[ABT PARTIAL: {abt_unique}]" if abt_unique else "[ABT MISSING]")

    print(f"  Adform : {adform_status}")
    print(f"  ABT    : {abt_status}")
    print(f"    Impression  : {imp_unique or 'none'}")
    print(f"    Click       : {clk_unique or 'none'}")
    print(f"    ABT orders  : {sorted(abt_unique) or 'none'}")

    return adform_status, abt_status


def run():
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

        print("\n[=== Consent Setup ===]")
        setup_consent(desktop_ctx, "https://www.eska.pl/")
        setup_consent(mobile_ctx,  "https://www.eska.pl/?force_mobile=1")

        results = []
        print("\n" + "="*60)
        print("eska.pl (ZPR) — BankClient Obligacje")
        print("="*60)

        for label, is_mobile, valid_bns, url in ESKA_URLS:
            ctx = mobile_ctx if is_mobile else desktop_ctx
            print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")
            adform_s, abt_s = check_url(ctx, label, valid_bns, url)
            results.append((label, adform_s, abt_s))

        browser.close()

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for label, adform_s, abt_s in results:
            print(f"  {adform_s:<35} {abt_s:<15} {label}")

        passed     = sum(1 for _, a, _ in results if a == "[PASS]")
        imp_ok_cnt = sum(1 for _, a, _ in results if "IMP OK" in a or a == "[PASS]")
        abt_ok_cnt = sum(1 for _, _, b in results if b == "[ABT OK]")
        total      = len(results)
        print(f"\n{passed}/{total} Adform fully verified (impression + click)")
        print(f"{imp_ok_cnt}/{total} Adform impressions OK")
        print(f"{abt_ok_cnt}/{total} ABT Shield OK")


if __name__ == "__main__":
    log = open("eska_results.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
