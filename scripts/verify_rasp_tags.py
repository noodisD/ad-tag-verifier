"""
Adform tag verification — RASP (kobieta.onet.pl)
BankClient Cyberbezpieczenstwo campaign
"""

from playwright.sync_api import sync_playwright
import re, time, sys

# ── RASP test URLs with expected bn= from xlsx ────────────────────────────────
# mobile=True → use mobile viewport (390x844)
RASP_URLS = [
    ("RASP 1260x300 YnvestPro r147030",    {90000001},         False, "https://kobieta.onet.pl/#adbeta=r147030!slot.top"),
    ("RASP 300x600 YnvestPro r147031",     {90000002},         False, "https://kobieta.onet.pl/#adbeta=r147031!slot.right"),
    ("RASP 600x500 YnvestPro r147032",     {90000003},         True,  "https://kobieta.onet.pl/?ress=mobile#adbeta=r147032!slot.right"),
    ("RASP 1260x300 Luksusowe r147022",    {90000004},         False, "https://kobieta.onet.pl/#adbeta=r147022!slot.top"),
    ("RASP 300x600 Luksusowe r147021",     {90000005},         False, "https://kobieta.onet.pl/#adbeta=r147021!slot.right"),
    ("RASP 600x500 Luksusowe r147023",     {90000006},         True,  "https://kobieta.onet.pl/?ress=mobile#adbeta=r147023!slot.right"),
    ("RASP BB_320x100 Luksusowe r147024",  {90000007},         True,  "https://kobieta.onet.pl/?ress=mobile#adbeta=r147024!slot.bottom-bar"),
    ("RASP 1260x300 Ryzyko r147026",       {90000008},         False, "https://kobieta.onet.pl/#adbeta=r147026!slot.top"),
    ("RASP 300x600 Ryzyko r147027",        {90000009},         False, "https://kobieta.onet.pl/#adbeta=r147027!slot.right"),
    ("RASP 600x500 Ryzyko r147028",        {90000010},         True,  "https://kobieta.onet.pl/?ress=mobile#adbeta=r147028!slot.right"),
    ("RASP BB_320x100 Ryzyko r147033",     {90000011},         True,  "https://kobieta.onet.pl/?ress=mobile#adbeta=r147033!slot.bottom-bar"),
    # r147029 labeled Ryzyko 320x100 but YnvestPro 320x100 has no other URL — accept either
    ("RASP BB_320x100 r147029 (Ryzyko?)",  {90000011, 90000012}, True, "https://kobieta.onet.pl/?ress=mobile#adbeta=r147029!slot.bottom-bar"),
]


def extract_bn(url):
    m = re.search(r'bn=(\d+)', url)
    return int(m.group(1)) if m else None


# ── Consent ───────────────────────────────────────────────────────────────────

CONSENT_SELECTORS = [
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj wszystko')",
    "button:has-text('Akceptuj')",           "button:has-text('Akceptuję')",
    "button:has-text('Zgadzam się')",        "button:has-text('Zgoda')",
    "button:has-text('Zezwól na wszystkie')", "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "#onetrust-accept-btn-handler", ".js-accept-all", "[class*='accept-all']",
    # Onet / Didomi / SourcePoint
    "button[data-cy='accept-all']", "#didomi-notice-agree-button",
    "button:has-text('Zgadzam się na wszystko')",
    # SourcePoint CMP
    "button.sp_choice_type_11", "[title='Accept All']", "[title='Akceptuj wszystkie']",
    "button:has-text('Wyrażam zgodę')", "button:has-text('Przyjmuję')",
    # Generic class patterns
    "[class*='consent'] button", "[id*='consent'] button",
    "[class*='agree']", "[class*='accept']",
]

def click_consent(page, ms=1500):
    # 1. Try direct selectors on main page
    for sel in CONSENT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=ms):
                btn.click()
                print(f"    [consent] {sel}")
                return True
        except Exception:
            pass

    # 2. Try inside every iframe (SourcePoint / custom CMP iframes)
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for sel in CONSENT_SELECTORS:
            try:
                btn = frame.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click()
                    print(f"    [consent-iframe] {sel} in {frame.url[:60]}")
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


# ── Scroll until ad fires ─────────────────────────────────────────────────────

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


# ── Core check ────────────────────────────────────────────────────────────────

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

    # Inline consent fallback
    if click_consent(page, ms=2000):
        try: page.wait_for_load_state("domcontentloaded", timeout=8000)
        except: pass
        t_ref[0] = time.time()
        impression_bns.clear()
        click_bns.clear()

    time.sleep(1.5)
    scroll_until_ad(page, impression_bns, click_bns)

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
        except Exception:
            pass

    page.close()

    imp_unique = list(set(impression_bns))
    clk_unique = list(set(click_bns))

    imp_ok = bool(imp_unique and (set(imp_unique) & valid_bns))
    clk_ok = bool(clk_unique and (set(clk_unique) & valid_bns))
    expected_str = "{" + ", ".join(str(b) for b in sorted(valid_bns)) + "}"

    status = ("[PASS]"                    if (imp_ok and clk_ok) else
              "[IMP OK / CLICK MISSING]"  if (imp_ok and not clk_ok) else
              "[FAIL - wrong bn]"         if (imp_unique or clk_unique) else
              "[NO AD FIRED]")

    print(f"  {status}")
    print(f"    Expected  : {expected_str}")
    print(f"    Impression: {imp_unique or 'none'}")
    print(f"    Click     : {clk_unique or 'none'}")
    return status


# ── Main ─────────────────────────────────────────────────────────────────────

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
        setup_consent(desktop_ctx, "https://kobieta.onet.pl/")
        setup_consent(mobile_ctx,  "https://kobieta.onet.pl/?ress=mobile")

        results = []

        print("\n" + "="*60)
        print("RASP — kobieta.onet.pl")
        print("="*60)
        for label, valid_bns, is_mobile, url in RASP_URLS:
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
        print("impressions verified OK")


if __name__ == "__main__":
    log = open("rasp_results.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
