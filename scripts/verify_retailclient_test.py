"""
Retailclient tag verification — all publishers from retailclient-test.xlsx
Checks CM360 impression (trackimp) + click (trackclk) with dc_trk_aid matching column E.
PASS = both impression AND click tag fired/found with the correct dc_trk_aid.
"""
from playwright.sync_api import sync_playwright
import re, time, sys, pandas as pd

# ── Load spreadsheet ──────────────────────────────────────────────────────────
df = pd.read_excel(r'./data/tags_export.xlsx', header=None)
rows = []
for i in range(1, len(df)):
    publisher = str(df.iloc[i, 0]).strip()
    fmt       = str(df.iloc[i, 1]).strip()
    device    = str(df.iloc[i, 2]).strip()
    url       = str(df.iloc[i, 3]).strip()
    ad_id     = str(df.iloc[i, 4]).strip()
    if not url or url == 'nan' or ad_id == 'nan':
        continue
    if url.startswith('olx.pl'):
        url = 'https://' + url
    rows.append((i, publisher, fmt, device, url, ad_id))

# ── Logging ───────────────────────────────────────────────────────────────────
log = open("retailclient_test_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

print(f"Loaded {len(rows)} rows from retailclient-test.xlsx")

# ── Helpers ───────────────────────────────────────────────────────────────────
def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all',
               'Zgadzam się','Przejdź do serwisu','I Accept','Agree']
    try:
        clicked = page.evaluate("""(phrases) => {
            for (const el of document.querySelectorAll('button, a')) {
                const t = (el.innerText || el.textContent || '').trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { el.click(); return t; }
            }
            return null;
        }""", phrases)
        if clicked:
            return True
    except:
        pass
    for sel in ["#onetrust-accept-btn-handler", ".fc-primary-button",
                "[class*='accept-all']", "[id*='accept-all']", ".cmp-accept-all"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click()
                return True
        except:
            pass
    return False

def dom_scan(page, ad_id):
    """Scan all frames for CM360 trackimp/trackclk with the expected dc_trk_aid."""
    found_imp = False
    found_clk = False
    for frame in page.frames:
        try:
            res = frame.evaluate("""(id) => {
                const h = document.documentElement ? document.documentElement.outerHTML : '';
                const imp = new RegExp('trackimp[^"\'<>\\\\s]*dc_trk_aid=' + id, 'i').test(h);
                const clk = new RegExp('trackclk[^"\'<>\\\\s]*dc_trk_aid=' + id, 'i').test(h);
                return {imp, clk};
            }""", ad_id)
            if res['imp']: found_imp = True
            if res['clk']: found_clk = True
        except:
            pass
    return found_imp, found_clk

def try_click_creative(page):
    """Try to click on the ad creative to trigger the click tracker."""
    # For DV360 preview: creative usually in an iframe
    for frame in page.frames:
        try:
            url = frame.url
            if 'doubleclick' in url or 'safeframe' in url or 'preview' in url.lower():
                box = frame.evaluate("() => ({w: document.body.scrollWidth, h: document.body.scrollHeight})")
                cx, cy = box['w'] // 2, box['h'] // 2
                if cx > 0 and cy > 0:
                    frame.evaluate(f"() => document.elementFromPoint({cx}, {cy})?.click()")
                    return True
        except:
            pass
    # Fallback: click center of the page
    try:
        vp = page.viewport_size
        if vp:
            page.mouse.click(vp['width'] // 2, vp['height'] // 2)
            return True
    except:
        pass
    return False

def make_context(browser, device):
    is_mobile = 'Mobile' in device
    return browser.new_context(
        viewport={"width": 390, "height": 844} if is_mobile
                  else {"width": 1280, "height": 900},
        locale="pl-PL",
        user_agent=("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
                    if is_mobile else
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        ignore_https_errors=True,
    )

# ── Main loop ─────────────────────────────────────────────────────────────────
results = []
consent_done = set()  # track which domains got consent so we share cookies

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # Pre-warm consent for publisher sites that need it
    print("\n[=== Consent Warmup ===]")
    consent_sites = [
        ("kobieta.gazeta.pl", "https://kobieta.gazeta.pl/", False),
        ("kobieta.wp.pl",     "https://kobieta.wp.pl/",     False),
        ("parenting.pl",      "https://parenting.pl/",      False),
        ("parenting.pl_m",    "https://parenting.pl/",      True),
        ("olx.pl",            "https://www.olx.pl/",        False),
        ("nto.pl",            "https://nto.pl/",            True),
    ]
    warmup_ctxs = {}
    for key, site, mobile in consent_sites:
        ctx = make_context(browser, "Mobile" if mobile else "Desktop")
        pg = ctx.new_page()
        try:
            pg.goto(site, wait_until="domcontentloaded", timeout=20000)
            pg.bring_to_front()
            time.sleep(5)
            res = click_consent(pg)
            time.sleep(2)
            print(f"  {'[mobile]' if mobile else '[desktop]'} {site} -- consent={res}")
        except Exception as e:
            print(f"  [warn] {site}: {e}")
        finally:
            pg.close()
        warmup_ctxs[key] = ctx

    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70)

    for i, (row_i, publisher, fmt, device, url, ad_id) in enumerate(rows):
        is_mobile = 'Mobile' in device
        print(f"\n[{i+1:2}/{len(rows)}] row={row_i} | {publisher} | {device}")
        print(f"        Ad ID : {ad_id}")
        print(f"        URL   : {url[:90]}")

        flags   = {"imp": False, "clk": False}
        t_ref   = [0.0]

        # Pick context: reuse warmed one for publisher sites, fresh for DV360/adquery
        domain = re.search(r'https?://([^/?]+)', url)
        domain = domain.group(1) if domain else ''

        if 'kobieta.gazeta.pl' in domain:
            ctx = warmup_ctxs["kobieta.gazeta.pl"]
            use_fresh = False
        elif 'kobieta.wp.pl' in domain:
            ctx = warmup_ctxs["kobieta.wp.pl"]
            use_fresh = False
        elif 'parenting.pl' in domain:
            ctx = warmup_ctxs["parenting.pl_m" if is_mobile else "parenting.pl"]
            use_fresh = False
        elif 'olx.pl' in domain:
            ctx = warmup_ctxs["olx.pl"]
            use_fresh = False
        elif 'nto.pl' in domain:
            ctx = warmup_ctxs["nto.pl"]
            use_fresh = False
        else:
            # DV360 preview and Adquery: fresh context each time
            ctx = make_context(browser, device)
            use_fresh = True

        page = ctx.new_page()

        def on_req(req, _ad_id=ad_id, _flags=flags, _t=t_ref):
            u = req.url
            if _ad_id not in u:
                return
            t = time.time() - _t[0] if _t[0] else 0
            if 'trackimp' in u and not _flags["imp"]:
                _flags["imp"] = True
                print(f"        [IMP NET t+{t:.0f}s] {u[:100]}")
            elif 'trackclk' in u and not _flags["clk"]:
                _flags["clk"] = True
                print(f"        [CLK NET t+{t:.0f}s] {u[:100]}")

        page.on("request", on_req)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"        [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(2)
        click_consent(page)
        time.sleep(4)

        # For WP / parenting: scroll to trigger lazy ads
        if 'wp.pl' in url or 'parenting.pl' in url:
            for _ in range(15):
                try: page.evaluate("window.scrollBy(0, 300)")
                except: pass
                time.sleep(0.4)
            time.sleep(2)

        imp_net = flags["imp"]
        clk_net = flags["clk"]

        # Try to click creative to trigger click tracker
        if not clk_net:
            try_click_creative(page)
            time.sleep(3)

        imp_net = flags["imp"]
        clk_net = flags["clk"]

        # DOM scan
        dom_imp, dom_clk = dom_scan(page, ad_id)
        if dom_imp and not imp_net:
            imp_net = True
            print(f"        [IMP DOM] dc_trk_aid={ad_id} in page source")
        if dom_clk and not clk_net:
            clk_net = True
            print(f"        [CLK DOM] dc_trk_aid={ad_id} in page source")

        if not imp_net and not clk_net:
            # Extra wait + second DOM scan
            time.sleep(6)
            dom_imp2, dom_clk2 = dom_scan(page, ad_id)
            imp_net = imp_net or flags["imp"]
            clk_net = clk_net or flags["clk"]
            if dom_imp2 and not imp_net:
                imp_net = True
                print(f"        [IMP DOM-2] dc_trk_aid={ad_id}")
            if dom_clk2 and not clk_net:
                clk_net = True
                print(f"        [CLK DOM-2] dc_trk_aid={ad_id}")

        page.close()
        if use_fresh:
            ctx.close()

        if imp_net and clk_net:
            status = "PASS"
        elif imp_net:
            status = "IMP ONLY"
        elif clk_net:
            status = "CLK ONLY"
        else:
            status = "NO TAG"

        print(f"        >> {status}")
        results.append((row_i, publisher, fmt, device, ad_id, status, imp_net, clk_net))

    browser.close()

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
passed = 0
for row_i, publisher, fmt, device, ad_id, status, imp, clk in results:
    mark = "[PASS]" if status == "PASS" else f"[{status}]"
    print(f"  {mark:<12} row={row_i:2} | {publisher:<8} | {device:<12} | id={ad_id}")
    if status == "PASS":
        passed += 1
    else:
        print(f"               IMP={imp}  CLK={clk}")

total = len(results)
print(f"\n{passed}/{total} PASS  |  {total-passed}/{total} need attention")

log.close()
