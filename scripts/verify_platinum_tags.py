"""
Adform tag verification — PLATINUM (Pudelek) + RASP Ryzyko re-check
BankClient Cyberbezpieczenstwo / Karta Platynowa
"""

from playwright.sync_api import sync_playwright
import re, time, sys

URLS = [
    # PLATINUM
    ("PLATINUM 600x400 Pudelek", {90000001}, False,
     "https://pudelek.pl?wfName=276551_3073523_BankClient_pakiet_giga_01&creName=600x400&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22200340%2F1459198%2Fiaq%2FBaner%2F1581576%22%7D%5D&testPos=1"),
    # RASP Ryzyko (already tested — re-confirming)
    ("RASP 1260x300 Ryzyko r147026", {90000002}, False, "https://kobieta.onet.pl/#adbeta=r147026!slot.top"),
    ("RASP 300x600 Ryzyko r147027",  {90000003}, False, "https://kobieta.onet.pl/#adbeta=r147027!slot.right"),
    ("RASP 600x500 Ryzyko r147028",  {90000004}, True,  "https://kobieta.onet.pl/?ress=mobile#adbeta=r147028!slot.right"),
    ("RASP BB_320x100 Ryzyko r147029", {90000005, 90000006}, True, "https://kobieta.onet.pl/?ress=mobile#adbeta=r147029!slot.bottom-bar"),
]

CONSENT_SELECTORS = [
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj wszystko')",
    "button:has-text('Akceptuj')",           "button:has-text('Akceptuję')",
    "button:has-text('Zgadzam się')",        "button:has-text('Zgoda')",
    "button:has-text('Zezwól na wszystkie')", "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "#onetrust-accept-btn-handler", ".js-accept-all", "[class*='accept-all']",
    "button[data-cy='accept-all']", "#didomi-notice-agree-button",
    "button:has-text('Zgadzam się na wszystko')",
    "button.sp_choice_type_11", "[title='Accept All']", "[title='Akceptuj wszystkie']",
    "button:has-text('Wyrażam zgodę')", "button:has-text('Przyjmuję')",
    "[class*='agree']", "[class*='accept']",
]

def extract_bn(url):
    m = re.search(r'bn=(\d+)', url)
    return int(m.group(1)) if m else None

def click_consent(page, ms=1500):
    for sel in CONSENT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=ms):
                btn.click()
                print(f"    [consent] {sel}")
                return True
        except Exception:
            pass
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for sel in CONSENT_SELECTORS:
            try:
                btn = frame.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click()
                    print(f"    [consent-iframe] {sel}")
                    return True
            except Exception:
                pass
    return False

def setup_consent(ctx, url):
    page = ctx.new_page()
    try:
        print(f"  [consent-setup] {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.bring_to_front()
        time.sleep(6)
        if click_consent(page, ms=3000):
            try: page.wait_for_load_state("domcontentloaded", timeout=8000)
            except: pass
            time.sleep(2)
            print(f"  [consent-setup] done")
        else:
            print(f"  [consent-setup] no popup found")
    except Exception as e:
        print(f"  [consent-setup] error: {e}")
    finally:
        page.close()

def scroll_until_ad(page, impression_bns, click_bns, step=250, pause=1.2, max_scrolls=100):
    for _ in range(max_scrolls):
        if impression_bns or click_bns:
            time.sleep(1.5)
            return True
        try:
            page_h = page.evaluate("document.body.scrollHeight") or 20000
            cur    = page.evaluate("window.pageYOffset + document.documentElement.clientHeight") or 0
            if cur >= page_h:
                break
            page.evaluate(f"window.scrollBy(0, {step})")
        except Exception:
            pass
        time.sleep(pause)
    return bool(impression_bns or click_bns)

def check_url(ctx, label, valid_bns, url):
    impression_bns = []
    click_bns = []
    t_ref = [0.0]

    def on_req(req):
        u = req.url
        if 'adform.net' not in u:
            return
        bn = extract_bn(u)
        if not bn:
            return
        t = time.time() - t_ref[0] if t_ref[0] else 0
        if 'adfserve' in u or '1x1inv' in u:
            if bn not in impression_bns:
                impression_bns.append(bn)
                print(f"    [IMP] bn={bn}  t+{t:.1f}s")
        elif '/C/' in u:
            if bn not in click_bns:
                click_bns.append(bn)
                print(f"    [CLK-net] bn={bn}  t+{t:.1f}s")

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

    time.sleep(1.5)
    scroll_until_ad(page, impression_bns, click_bns)

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
        except Exception:
            pass

    page.close()

    imp_unique = list(set(impression_bns))
    clk_unique = list(set(click_bns))
    imp_ok = bool(imp_unique and (set(imp_unique) & valid_bns))
    clk_ok = bool(clk_unique and (set(clk_unique) & valid_bns))
    expected_str = "{" + ", ".join(str(b) for b in sorted(valid_bns)) + "}"

    status = ("[PASS]"                   if (imp_ok and clk_ok) else
              "[IMP OK / CLICK MISSING]" if (imp_ok and not clk_ok) else
              "[FAIL - wrong bn]"        if (imp_unique or clk_unique) else
              "[NO AD FIRED]")

    print(f"  {status}")
    print(f"    Expected  : {expected_str}")
    print(f"    Impression: {imp_unique or 'none'}")
    print(f"    Click     : {clk_unique or 'none'}")
    return status


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
        setup_consent(desktop_ctx, "https://www.pudelek.pl/")
        setup_consent(desktop_ctx, "https://kobieta.onet.pl/")
        setup_consent(mobile_ctx,  "https://kobieta.onet.pl/?ress=mobile")

        results = []
        print("\n" + "="*60)
        for label, valid_bns, is_mobile, url in URLS:
            ctx = mobile_ctx if is_mobile else desktop_ctx
            print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")
            status = check_url(ctx, label, valid_bns, url)
            results.append((label, status))

        browser.close()

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for label, status in results:
            print(f"  {status:<35} {label}")
        passed = sum(1 for _, s in results if s == "[PASS]")
        imp_ok = sum(1 for _, s in results if "IMP OK" in s or s == "[PASS]")
        total  = len(results)
        print(f"\n{passed}/{total} fully verified (impression + click)")
        print(f"{imp_ok}/{total} impressions verified OK")


if __name__ == "__main__":
    log = open("platinum_results.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
