"""
Adform + ABT Shield tag verification — Interia (kobieta.interia.pl)
BankClient Obligacje campaign — Linia3 & Linia4
"""

from playwright.sync_api import sync_playwright
import re, time, sys

# Expected bn= per URL (Polsat Media Multiscreen rows from xlsx)
# DRM = FIX deal type
INTERIA_URLS = [
    # Linia3 CPM
    ("Interia Linia3 CPM 1220x300", {90000001}, "https://kobieta.interia.pl/#adtester2023_6a1d95e334223b667ab17f16"),
    ("Interia Linia3 CPM 300x250",  {90000002}, "https://kobieta.interia.pl/#adtester2023_6a1d95e934223b667ab17f23"),
    # Linia3 DRM
    ("Interia Linia3 DRM 1220x300", {90000003}, "https://kobieta.interia.pl/#adtester2023_6a1d900000043b667ab17fab"),
    ("Interia Linia3 DRM 300x250",  {90000005}, "https://kobieta.interia.pl/#adtester2023_6a1d900000063b667ab17fb8"),
    # Linia4 CPM
    ("Interia Linia4 CPM 1220x300", {90000007}, "https://kobieta.interia.pl/#adtester2023_6a1d95ee34223b667ab17f30"),
    ("Interia Linia4 CPM 300x250",  {90000008}, "https://kobieta.interia.pl/#adtester2023_6a1d95f434223b667ab17f3d"),
    # Linia4 DRM
    ("Interia Linia4 DRM 1220x300", {90000009}, "https://kobieta.interia.pl/#adtester2023_6a1d967e34223b667ab17fc5"),
    ("Interia Linia4 DRM 300x250",  {90000010}, "https://kobieta.interia.pl/#adtester2023_6a1d900000113b667ab17fd2"),
]

# Both ABT Shield sinks must fire on every page
ABT_EXPECTED = {"900000122", "900000132"}

CONSENT_SELECTORS = [
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj wszystko')",
    "button:has-text('Akceptuj')", "button:has-text('Akceptuję')",
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
    for sel in CONSENT_SELECTORS:
        try:
            if page.locator(sel).first.is_visible(timeout=ms):
                page.locator(sel).first.click()
                print(f"    [consent] {sel}")
                return True
        except: pass
    for frame in page.frames:
        if frame == page.main_frame: continue
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
        time.sleep(6)
        if click_consent(page, ms=3000):
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

    if click_consent(page, ms=2000):
        try: page.wait_for_load_state("domcontentloaded", timeout=8000)
        except: pass
        t_ref[0] = time.time()
        impression_bns.clear()
        click_bns.clear()
        abt_orders.clear()

    time.sleep(1.5)

    # Scroll until ad fires or full page traversed
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

    # Extra wait for ABT Shield (fires after ad loads)
    time.sleep(2)

    # DOM scan for click URLs
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
    expected_str = "{" + ", ".join(str(b) for b in sorted(valid_bns)) + "}"

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
    print(f"    Expected bn : {expected_str}")
    print(f"    Impression  : {imp_unique or 'none'}")
    print(f"    Click       : {clk_unique or 'none'}")
    print(f"    ABT orders  : {sorted(abt_unique) or 'none'}")

    return adform_status, abt_status


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="pl-PL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        print("\n[=== Consent Setup ===]")
        setup_consent(ctx, "https://kobieta.interia.pl/")

        results = []
        print("\n" + "="*60)
        print("Interia — kobieta.interia.pl — BankClient Obligacje")
        print("="*60)

        for label, valid_bns, url in INTERIA_URLS:
            print(f"\n[{label}]")
            adform_s, abt_s = check_url(ctx, label, valid_bns, url)
            results.append((label, adform_s, abt_s))

        browser.close()

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for label, adform_s, abt_s in results:
            print(f"  {adform_s:<35} {abt_s:<20} {label}")

        passed     = sum(1 for _, a, _ in results if a == "[PASS]")
        imp_ok_cnt = sum(1 for _, a, _ in results if "IMP OK" in a or a == "[PASS]")
        abt_ok_cnt = sum(1 for _, _, b in results if b == "[ABT OK]")
        total      = len(results)
        print(f"\n{passed}/{total} Adform fully verified (impression + click)")
        print(f"{imp_ok_cnt}/{total} Adform impressions OK")
        print(f"{abt_ok_cnt}/{total} ABT Shield fully OK (both o= values)")


if __name__ == "__main__":
    log = open("interia_results.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
