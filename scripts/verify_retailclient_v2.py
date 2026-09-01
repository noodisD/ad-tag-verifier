"""
Retailclient tag verification v2 — all 39 rows.
Improvements vs v1:
  - DV360 preview: clicks outer iframe first to trigger creative load, then
    clicks inside creative frame to capture trackclk
  - Blocks landing-page navigations (keeps context alive after click)
  - Proper mobile context for each row (not shared desktop ctx for mobile GAM)
  - Longer wait for impression (15s for DV360)
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

log = open("retailclient_v2_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)
print(f"Loaded {len(rows)} rows")

# ── Helpers ───────────────────────────────────────────────────────────────────
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_MOBILE  = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36")

def make_ctx(browser, device):
    mob = 'Mobile' in device
    return browser.new_context(
        viewport={"width": 390, "height": 844} if mob else {"width": 1280, "height": 900},
        locale="pl-PL",
        user_agent=UA_MOBILE if mob else UA_DESKTOP,
        ignore_https_errors=True,
    )

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all',
               'Zgadzam się','Przejdź do serwisu','AKCEPTUJĘ']
    try:
        clicked = page.evaluate("""(phrases) => {
            for (const el of document.querySelectorAll('button, a')) {
                const t = (el.innerText || el.textContent || '').trim().toUpperCase();
                if (phrases.some(p => t === p.toUpperCase() || t.startsWith(p.toUpperCase()))) {
                    el.click(); return t;
                }
            }
            return null;
        }""", phrases)
        if clicked: return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler", ".fc-primary-button",
                "[class*='cmp-accept']", "[data-cmp-exp='acceptAll']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click(); return True
        except: pass
    return False

def block_landings(route):
    """Allow tracking / ad domains; abort everything else after creative loads."""
    u = route.request.url
    allowed = any(d in u for d in [
        'doubleclick.net', 'google.com', 'googleusercontent.com',
        'adsystem.com', 'googlesyndication.com', 'adform.net',
        'facebook.com', 'tiktok.com', 'adquery.io', 'adnxs.com',
        'kobieta.wp.pl', 'parenting.pl', 'kobieta.gazeta.pl',
        'olx.pl', 'nto.pl', 'displayvideo', 'gstatic.com',
        'google-analytics', 'analytics', 'cdn', '.css', '.js', '.png',
        '.jpg', '.svg', '.woff', '.ico', 'fonts', 'cdn.', 'static.',
    ])
    try:
        if allowed: route.continue_()
        else:        route.abort()
    except: pass

def dom_scan(page, ad_id):
    found_imp = found_clk = False
    for frame in page.frames:
        try:
            res = frame.evaluate("""(id) => {
                const h = document.documentElement ? document.documentElement.outerHTML : '';
                const imp = /trackimp[^\s"'<>]*dc_trk_aid=/.test(h) && h.includes('dc_trk_aid=' + id);
                const clk = /trackclk[^\s"'<>]*dc_trk_aid=/.test(h) && h.includes('dc_trk_aid=' + id)
                          || /trackclkns[^\s"'<>]*dc_trk_aid=/.test(h) && h.includes('dc_trk_aid=' + id);
                return {imp, clk};
            }""", ad_id)
            if res['imp']: found_imp = True
            if res['clk']: found_clk = True
        except: pass
    return found_imp, found_clk

def click_inside_creative(page, flags):
    """After impression fires, try to click inside the creative iframe."""
    # Find frames from adspreview (DV360) or safeframe (GAM)
    for frame in page.frames:
        try:
            fu = frame.url
            if not fu or fu in ('about:blank', ''):
                continue
            is_creative = ('adspreview.googleusercontent.com' in fu
                           or 'safeframe' in fu
                           or 'tpc.googlesyndication' in fu
                           or 'doubleclick.net/safeframe' in fu)
            if not is_creative:
                continue
            # Click body element directly via JS
            frame.evaluate("""() => {
                const a = document.querySelector('a');
                if (a) { a.click(); return; }
                const el = document.elementFromPoint(
                    document.body.scrollWidth/2,
                    document.body.scrollHeight/2);
                if (el) el.click();
            }""")
            return True
        except: pass

    # Fallback: click at the center of each large iframe on the main page
    try:
        for iframe_el in page.locator("iframe").all():
            box = iframe_el.bounding_box()
            if box and box['width'] > 100 and box['height'] > 50:
                page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                time.sleep(1)
    except: pass
    return False

# ── Consent warmup ────────────────────────────────────────────────────────────
print("\n[=== Consent Warmup ===]")
results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # Warm up shared contexts for publisher sites
    shared_ctxs = {}
    warmup_list = [
        ("kobieta.gazeta.pl_d", "https://kobieta.gazeta.pl/", False),
        ("kobieta.gazeta.pl_m", "https://kobieta.gazeta.pl/", True),
        ("kobieta.wp.pl",       "https://kobieta.wp.pl/",     False),
        ("parenting.pl_d",      "https://parenting.pl/",      False),
        ("parenting.pl_m",      "https://parenting.pl/",      True),
        ("olx.pl",              "https://www.olx.pl/",        False),
        ("nto.pl_m",            "https://nto.pl/",            True),
    ]
    for key, site, mobile in warmup_list:
        ctx = make_ctx(browser, "Mobile" if mobile else "Desktop")
        pg = ctx.new_page()
        try:
            pg.goto(site, wait_until="domcontentloaded", timeout=20000)
            pg.bring_to_front(); time.sleep(5)
            ok = click_consent(pg); time.sleep(2)
            print(f"  {'mob' if mobile else 'dsk'} {site} consent={ok}")
        except Exception as e:
            print(f"  [warn] {site}: {e}")
        finally:
            pg.close()
        shared_ctxs[key] = ctx

    print("\n" + "="*70)
    print("VERIFICATION v2")
    print("="*70)

    for i, (row_i, publisher, fmt, device, url, ad_id) in enumerate(rows):
        is_mobile = 'Mobile' in device
        is_dv360  = 'displayvideo.google.com' in url
        is_adquery = 'adquery.io' in url

        print(f"\n[{i+1:2}/{len(rows)}] row={row_i} | {publisher} | {device} | id={ad_id}")
        print(f"        URL: {url[:80]}")

        # Pick context
        domain = re.search(r'https?://([^/?]+)', url)
        domain = domain.group(1) if domain else ''

        if is_dv360 or is_adquery:
            ctx = make_ctx(browser, device)
            owned = True
        elif 'kobieta.gazeta.pl' in domain:
            ctx = shared_ctxs["kobieta.gazeta.pl_m" if is_mobile else "kobieta.gazeta.pl_d"]
            owned = False
        elif 'wp.pl' in domain:
            ctx = shared_ctxs["kobieta.wp.pl"]
            owned = False
        elif 'parenting.pl' in domain:
            ctx = shared_ctxs["parenting.pl_m" if is_mobile else "parenting.pl_d"]
            owned = False
        elif 'olx.pl' in domain:
            ctx = shared_ctxs["olx.pl"]
            owned = False
        elif 'nto.pl' in domain:
            ctx = shared_ctxs["nto.pl_m"]
            owned = False
        else:
            ctx = make_ctx(browser, device)
            owned = True

        page = ctx.new_page()
        flags = {"imp": False, "clk": False}
        t_ref = [0.0]

        def on_req(req, _ad=ad_id, _f=flags, _t=t_ref):
            u = req.url
            if _ad not in u: return
            t = time.time() - _t[0] if _t[0] else 0
            if 'trackimp' in u and not _f["imp"]:
                _f["imp"] = True
                print(f"        [IMP t+{t:.0f}s] {u[:110]}")
            elif 'trackclk' in u and not _f["clk"]:
                _f["clk"] = True
                print(f"        [CLK t+{t:.0f}s] {u[:110]}")

        page.on("request", on_req)
        # Block landings only for DV360/adquery (otherwise publisher page breaks)
        if is_dv360 or is_adquery:
            page.route("**", block_landings)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"        [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(2)
        click_consent(page)
        time.sleep(2)

        if is_dv360:
            # Phase 1: click outer DV360 iframe to trigger creative load
            try:
                iframes = page.locator("iframe").all()
                if iframes:
                    box = iframes[0].bounding_box()
                    if box:
                        cx = box['x'] + box['width'] / 2
                        cy = box['y'] + box['height'] / 2
                        page.mouse.click(cx, cy)
            except: pass
            # Wait for impression (up to 15s)
            deadline = time.time() + 15
            while time.time() < deadline and not flags["imp"]:
                time.sleep(0.5)
            time.sleep(1)

            # Phase 2: click inside the creative to trigger click tag
            if not flags["clk"]:
                click_inside_creative(page, flags)
                deadline = time.time() + 5
                while time.time() < deadline and not flags["clk"]:
                    time.sleep(0.5)

        elif is_adquery:
            time.sleep(10)
            if not flags["clk"]:
                try: page.mouse.click(195, 400)
                except: pass
                click_inside_creative(page, flags)
                time.sleep(5)

        else:
            # Publisher site
            if 'wp.pl' in url or 'parenting.pl' in url:
                for _ in range(12):
                    try: page.evaluate("window.scrollBy(0, 250)")
                    except: pass
                    time.sleep(0.4)
            time.sleep(5)
            # Try to click on the ad creative
            if not flags["clk"]:
                click_inside_creative(page, flags)
                time.sleep(5)

        imp_net = flags["imp"]
        clk_net = flags["clk"]

        # DOM scan as additional check
        dom_imp, dom_clk = dom_scan(page, ad_id)
        if dom_imp and not imp_net:
            imp_net = True; print(f"        [IMP DOM]")
        if dom_clk and not clk_net:
            clk_net = True; print(f"        [CLK DOM]")

        # Extra wait if nothing yet
        if not imp_net:
            time.sleep(6)
            imp_net = imp_net or flags["imp"]
            clk_net = clk_net or flags["clk"]
            d2, c2 = dom_scan(page, ad_id)
            if d2 and not imp_net: imp_net = True; print(f"        [IMP DOM-2]")
            if c2 and not clk_net: clk_net = True; print(f"        [CLK DOM-2]")

        page.close()
        if owned: ctx.close()

        if imp_net and clk_net:   status = "PASS"
        elif imp_net:             status = "IMP ONLY"
        elif clk_net:             status = "CLK ONLY"
        else:                     status = "NO TAG"

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
    if status != "PASS":
        print(f"               imp={imp} clk={clk}")
    if status == "PASS": passed += 1

print(f"\n{passed}/{len(results)} PASS  |  {len(results)-passed}/{len(results)} need attention")
log.close()
