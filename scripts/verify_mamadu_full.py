"""Capture ALL dc_trk_aid values on each mamadu.pl adTest page."""
from playwright.sync_api import sync_playwright
import re, time, collections

TESTS = [
    ("image",   "900000013", "https://mamadu.pl/212554,5-zachowan-ktore-zostaly-z-toba-od-dziecinstwa-to-wszystko-dlatego-ze-balas-sie-reakcji-mamy?adTest=image"),
    ("product", "900000021", "https://mamadu.pl/212554,5-zachowan-ktore-zostaly-z-toba-od-dziecinstwa-to-wszystko-dlatego-ze-balas-sie-reakcji-mamy?adTest=product"),
]

UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all','Zgadzam się','AKCEPTUJĘ',
               'Akceptuj i przejdź','Przejdź do serwisu']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t = (el.innerText||el.textContent||'').trim().toUpperCase();
                if (p.some(x => t===x.toUpperCase()||t.startsWith(x.toUpperCase()))) {el.click(); return t;}
            } return null;
        }""", phrases)
        if ok: print(f"    [consent] {ok}"); return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']",
                ".cmp__btn--accept-all","[class*='accept-all']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); print(f"    [consent-sel] {sel}"); return True
        except: pass
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    ctx = browser.new_context(viewport={"width":1280,"height":900}, locale="pl-PL",
                               user_agent=UA_D, ignore_https_errors=True)

    # Warmup consent
    print("[warmup] mamadu.pl")
    pg0 = ctx.new_page()
    pg0.goto("https://mamadu.pl/", wait_until="domcontentloaded", timeout=20000)
    pg0.bring_to_front(); time.sleep(5)
    click_consent(pg0); time.sleep(2)
    pg0.close()

    for label, expected_id, url in TESTS:
        print(f"\n{'='*65}")
        print(f"[{label}] expected id={expected_id}")

        # Fresh context per page to avoid frequency capping
        page_ctx = browser.new_context(viewport={"width":1280,"height":900}, locale="pl-PL",
                                        user_agent=UA_D, ignore_https_errors=True)

        tags = collections.defaultdict(lambda: {"imp": False, "clk": False})
        t_ref = [0.0]

        def on_req(req, _tags=tags, _t=t_ref):
            u = req.url
            if 'doubleclick.net' not in u and 'dc_trk' not in u:
                return
            m = re.search(r'dc_trk_aid=(\d+)', u)
            if not m:
                return
            aid = m.group(1)
            t = time.time() - _t[0] if _t[0] else 0
            if 'trackimp' in u and not _tags[aid]["imp"]:
                _tags[aid]["imp"] = True
                print(f"    [IMP t+{t:.0f}s] aid={aid}")
            elif 'trackclk' in u and not _tags[aid]["clk"]:
                _tags[aid]["clk"] = True
                print(f"    [CLK t+{t:.0f}s] aid={aid}")

        page = page_ctx.new_page()
        page.on("request", on_req)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3)
        click_consent(page)
        time.sleep(3)
        click_consent(page)
        time.sleep(3)

        # Get full page height and scroll step by step
        try:
            total_h = page.evaluate("document.body.scrollHeight")
            print(f"  [page height: {total_h}px — scrolling in steps...]")
        except:
            total_h = 10000

        step = 300
        pos = 0
        while pos < total_h + 2000:
            try: page.evaluate(f"window.scrollTo(0, {pos})")
            except: pass
            time.sleep(0.4)
            pos += step
            # Refresh total height (infinite scroll / lazy load)
            try:
                new_h = page.evaluate("document.body.scrollHeight")
                if new_h > total_h:
                    total_h = new_h
            except: pass

        # Back to top then wait for any delayed requests
        try: page.evaluate("window.scrollTo(0, 0)")
        except: pass
        time.sleep(10)

        # One more slow scroll pass
        pos = 0
        while pos < total_h:
            try: page.evaluate(f"window.scrollTo(0, {pos})")
            except: pass
            time.sleep(0.3)
            pos += 600

        time.sleep(10)

        print(f"\n  --- Results for [{label}] ({len(tags)} unique aids found) ---")
        if not tags:
            print("  NO CM360 tags found at all")
        else:
            for aid, st in sorted(tags.items()):
                imp_ok = "OK" if st["imp"] else "--"
                clk_ok = "OK" if st["clk"] else "--"
                match = " <-- EXPECTED" if aid == expected_id else ""
                status = "PASS" if st["imp"] and st["clk"] else "IMP ONLY" if st["imp"] else "CLK ONLY" if st["clk"] else "?"
                print(f"  [{status}] aid={aid}  imp={imp_ok}  clk={clk_ok}{match}")

        page.close()
        page_ctx.close()

    ctx.close()
    browser.close()

print("\nDone.")
