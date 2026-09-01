"""Deep scan — shared context, 60s wait, full impression URLs for all aids."""
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
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']",".cmp__btn--accept-all"]:
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
    pg0.bring_to_front(); time.sleep(6)
    click_consent(pg0); time.sleep(3)
    pg0.close()

    for label, expected_id, url in TESTS:
        print(f"\n{'='*65}")
        print(f"[{label}] expected id={expected_id}")

        # {aid: {"imp": url|None, "clk": url|None}}
        tags = collections.defaultdict(lambda: {"imp": None, "clk": None})
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
            if 'trackimp' in u and _tags[aid]["imp"] is None:
                _tags[aid]["imp"] = u
                print(f"    [IMP t+{t:.0f}s] aid={aid}  {u[35:110]}")
            elif 'trackclk' in u and _tags[aid]["clk"] is None:
                _tags[aid]["clk"] = u
                print(f"    [CLK t+{t:.0f}s] aid={aid}")

        page = ctx.new_page()
        page.on("request", on_req)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3)
        click_consent(page); time.sleep(3)
        click_consent(page); time.sleep(3)

        # Scroll entire page slowly
        try:
            total_h = page.evaluate("document.body.scrollHeight")
        except:
            total_h = 15000
        print(f"  [page height: {total_h}px]")

        pos = 0
        while pos < total_h + 3000:
            try: page.evaluate(f"window.scrollTo(0, {pos})")
            except: pass
            time.sleep(0.5)
            pos += 250
            try:
                new_h = page.evaluate("document.body.scrollHeight")
                if new_h > total_h: total_h = new_h
            except: pass

        print("  [waiting 20s for delayed ads...]")
        try: page.evaluate("window.scrollTo(0, 0)")
        except: pass
        time.sleep(10)

        # Second scroll pass
        pos = 0
        while pos < total_h:
            try: page.evaluate(f"window.scrollTo(0, {pos})")
            except: pass
            time.sleep(0.4)
            pos += 500

        time.sleep(10)

        print(f"\n  --- [{label}] SUMMARY: {len(tags)} unique aid(s) found ---")
        for aid, st in sorted(tags.items()):
            imp_ok = "OK" if st["imp"] else "--"
            clk_ok = "OK" if st["clk"] else "--"
            exp = " <-- EXPECTED" if aid == expected_id else ""
            status = "PASS" if st["imp"] and st["clk"] else "IMP ONLY" if st["imp"] else "CLK ONLY" if st["clk"] else "?"
            print(f"  [{status}] {aid}  imp={imp_ok}  clk={clk_ok}{exp}")
            # Print full imp URL so we can see campaign/placement info
            if st["imp"]:
                print(f"    imp URL: {st['imp'][:140]}")

        page.close()

    ctx.close()
    browser.close()

print("\nDone.")
