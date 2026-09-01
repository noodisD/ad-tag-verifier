"""
Retailclient tag verification v3 — all 39 rows.
Key fixes vs v2:
  - No route blocking (was interfering with DV360 loading)
  - Track which frame fired the impression, then click inside it for click tag
  - Longer deadline for impression (25s after iframe click)
  - Keep checking flags until page.close()
"""
from playwright.sync_api import sync_playwright
import re, time, sys, pandas as pd

df = pd.read_excel(r'./data/tags_export.xlsx', header=None)
rows = []
for i in range(1, len(df)):
    publisher = str(df.iloc[i, 0]).strip()
    fmt       = str(df.iloc[i, 1]).strip()
    device    = str(df.iloc[i, 2]).strip()
    url       = str(df.iloc[i, 3]).strip()
    ad_id     = str(df.iloc[i, 4]).strip()
    if not url or url == 'nan' or ad_id == 'nan': continue
    if url.startswith('olx.pl'): url = 'https://' + url
    rows.append((i, publisher, fmt, device, url, ad_id))

log = open("retailclient_v3_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)
print(f"Loaded {len(rows)} rows")

UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

def make_ctx(browser, device):
    mob = 'Mobile' in device
    return browser.new_context(
        viewport={"width": 390, "height": 844} if mob else {"width": 1280, "height": 900},
        locale="pl-PL", user_agent=UA_M if mob else UA_D, ignore_https_errors=True)

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all','Zgadzam się','AKCEPTUJĘ']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t = (el.innerText||el.textContent||'').trim().toUpperCase();
                if (p.some(x => t===x.toUpperCase()||t.startsWith(x.toUpperCase()))) {el.click();return t;}
            } return null;
        }""", phrases)
        if ok: return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click(); return True
        except: pass
    return False

def dom_scan(page, ad_id):
    fi = fc = False
    for frame in page.frames:
        try:
            r = frame.evaluate("""(id) => {
                const h = (document.documentElement||document.body||{}).outerHTML||'';
                return {
                    imp: h.includes('trackimp') && h.includes('dc_trk_aid='+id),
                    clk: (h.includes('trackclk')||h.includes('trackclkns')) && h.includes('dc_trk_aid='+id)
                };
            }""", ad_id)
            if r['imp']: fi = True
            if r['clk']: fc = True
        except: pass
    return fi, fc

results = []

print("\n[=== Consent Warmup ===]")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    shared = {}
    for key, site, mob in [
        ("gazeta_d","https://kobieta.gazeta.pl/",False),
        ("gazeta_m","https://kobieta.gazeta.pl/",True),
        ("wp",      "https://kobieta.wp.pl/",    False),
        ("parent_d","https://parenting.pl/",     False),
        ("parent_m","https://parenting.pl/",     True),
        ("olx",     "https://www.olx.pl/",       False),
        ("nto_m",   "https://nto.pl/",           True),
    ]:
        ctx = make_ctx(browser, "Mobile" if mob else "Desktop")
        pg  = ctx.new_page()
        try:
            pg.goto(site, wait_until="domcontentloaded", timeout=20000)
            pg.bring_to_front(); time.sleep(5)
            ok = click_consent(pg); time.sleep(2)
            print(f"  {'mob' if mob else 'dsk'} {site} consent={ok}")
        except Exception as e:
            print(f"  [warn] {site}: {e}")
        finally:
            pg.close()
        shared[key] = ctx

    print("\n" + "="*70)
    print("VERIFICATION v3")
    print("="*70)

    for i, (row_i, publisher, fmt, device, url, ad_id) in enumerate(rows):
        is_mob    = 'Mobile' in device
        is_dv360  = 'displayvideo.google.com' in url
        is_adq    = 'adquery.io' in url
        dom       = re.search(r'https?://([^/?]+)', url)
        dom       = dom.group(1) if dom else ''

        print(f"\n[{i+1:2}/{len(rows)}] row={row_i} | {publisher} | {device} | id={ad_id}")
        print(f"        URL: {url[:80]}")

        if is_dv360 or is_adq:
            ctx = make_ctx(browser, device); owned = True
        elif 'kobieta.gazeta.pl' in dom:
            ctx = shared["gazeta_m" if is_mob else "gazeta_d"]; owned = False
        elif 'wp.pl' in dom:
            ctx = shared["wp"]; owned = False
        elif 'parenting.pl' in dom:
            ctx = shared["parent_m" if is_mob else "parent_d"]; owned = False
        elif 'olx.pl' in dom:
            ctx = shared["olx"]; owned = False
        elif 'nto.pl' in dom:
            ctx = shared["nto_m"]; owned = False
        else:
            ctx = make_ctx(browser, device); owned = True

        page    = ctx.new_page()
        flags   = {"imp": False, "clk": False}
        imp_frame = [None]
        t_ref   = [0.0]

        def on_req(req, _ad=ad_id, _f=flags, _t=t_ref, _fr=imp_frame):
            u = req.url
            if _ad not in u: return
            t = time.time() - _t[0] if _t[0] else 0
            if 'trackimp' in u and not _f["imp"]:
                _f["imp"] = True
                _fr[0] = req.frame
                print(f"        [IMP t+{t:.0f}s] {u[:110]}")
            elif 'trackclk' in u and not _f["clk"]:
                _f["clk"] = True
                print(f"        [CLK t+{t:.0f}s] {u[:110]}")

        page.on("request", on_req)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"        [load err] {e}")
        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(2)
        click_consent(page)
        time.sleep(2)

        if is_dv360:
            # Click center of viewport to trigger creative load
            try: page.mouse.click(640, 450)
            except: pass
            # Wait for impression up to 25s
            deadline = time.time() + 25
            while time.time() < deadline and not flags["imp"]:
                time.sleep(0.5)
            time.sleep(1)

            # Click inside the creative frame to trigger click tag
            if not flags["clk"]:
                clicked_creative = False
                # Try the frame that fired the impression first
                if imp_frame[0]:
                    try:
                        imp_frame[0].evaluate("""() => {
                            const a = document.querySelector('a');
                            if (a) { a.click(); return; }
                            const el = document.elementFromPoint(
                                document.body.scrollWidth/2,
                                document.body.scrollHeight/2);
                            if (el) el.click();
                        }""")
                        clicked_creative = True
                    except: pass
                # Also try adspreview frames
                if not clicked_creative:
                    for frame in page.frames:
                        try:
                            if 'adspreview' in frame.url or 'safeframe' in frame.url:
                                frame.evaluate("""() => {
                                    const a = document.querySelector('a');
                                    if (a) a.click();
                                    else document.body.click();
                                }""")
                                break
                        except: pass
                # Wait for click tag
                deadline2 = time.time() + 8
                while time.time() < deadline2 and not flags["clk"]:
                    time.sleep(0.5)

        elif is_adq:
            time.sleep(8)
            try: page.mouse.click(195, 400)
            except: pass
            deadline = time.time() + 8
            while time.time() < deadline and not flags["clk"]:
                time.sleep(0.5)

        else:
            # Publisher site: scroll for WP/parenting, wait for impression
            if 'wp.pl' in url or 'parenting.pl' in url:
                for _ in range(12):
                    try: page.evaluate("window.scrollBy(0,250)")
                    except: pass
                    time.sleep(0.4)
            time.sleep(5)
            # Try clicking on the ad unit
            if not flags["clk"]:
                for frame in page.frames:
                    try:
                        fu = frame.url
                        if not fu or fu == 'about:blank': continue
                        if ('safeframe' in fu or 'tpc.googlesyndication' in fu
                                or 'doubleclick.net' in fu or 'adform' in fu
                                or 'adquery.io' in fu):
                            frame.evaluate("""() => {
                                const a = document.querySelector('a');
                                if (a) a.click();
                                else document.body.click();
                            }""")
                    except: pass
                deadline = time.time() + 6
                while time.time() < deadline and not flags["clk"]:
                    time.sleep(0.5)

        # Capture final state
        imp_net = flags["imp"]
        clk_net = flags["clk"]

        # DOM scan
        di, dc = dom_scan(page, ad_id)
        if di and not imp_net: imp_net = True; print(f"        [IMP DOM]")
        if dc and not clk_net: clk_net = True; print(f"        [CLK DOM]")

        # Extra 6s wait if nothing found yet
        if not imp_net:
            time.sleep(6)
            imp_net = imp_net or flags["imp"]
            clk_net = clk_net or flags["clk"]
            di2, dc2 = dom_scan(page, ad_id)
            if di2 and not imp_net: imp_net = True; print(f"        [IMP DOM-2]")
            if dc2 and not clk_net: clk_net = True; print(f"        [CLK DOM-2]")

        page.close()
        if owned: ctx.close()

        if   imp_net and clk_net: status = "PASS"
        elif imp_net:             status = "IMP ONLY"
        elif clk_net:             status = "CLK ONLY"
        else:                     status = "NO TAG"

        print(f"        >> {status}")
        results.append((row_i, publisher, fmt, device, ad_id, status, imp_net, clk_net))

    browser.close()

print("\n" + "="*70)
print("SUMMARY")
print("="*70)
passed = imp_ok = 0
for row_i, pub, fmt, dev, aid, status, imp, clk in results:
    mark = "[PASS]" if status == "PASS" else f"[{status}]"
    print(f"  {mark:<12} row={row_i:2} | {pub:<8} | {dev:<12} | id={aid}")
    if status != "PASS":
        print(f"               imp={imp}  clk={clk}")
    if status == "PASS": passed += 1
    if imp: imp_ok += 1

print(f"\n{passed}/{len(results)} PASS  |  {imp_ok}/{len(results)} IMP confirmed  |  {len(results)-imp_ok}/{len(results)} need attention")
log.close()
