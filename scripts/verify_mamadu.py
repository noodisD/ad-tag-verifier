"""Verify mamadu.pl adTest URLs — impression + click tags for both IDs."""
from playwright.sync_api import sync_playwright
import time

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
                ".cmp__btn--accept-all","[class*='accept-all']","[class*='consent-accept']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); print(f"    [consent-sel] {sel}"); return True
        except: pass
    return False

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # Consent warmup for mamadu.pl
    print("[warmup] mamadu.pl")
    ctx0 = browser.new_context(viewport={"width":1280,"height":900}, locale="pl-PL",
                                user_agent=UA_D, ignore_https_errors=True)
    pg0 = ctx0.new_page()
    pg0.goto("https://mamadu.pl/", wait_until="domcontentloaded", timeout=20000)
    pg0.bring_to_front(); time.sleep(5)
    ok = click_consent(pg0); time.sleep(2)
    print(f"  consent={ok}")
    pg0.close()

    for label, ad_id, url in TESTS:
        print(f"\n{'='*60}")
        print(f"[{label}] id={ad_id}")
        print(f"  {url}")

        page = ctx0.new_page()
        flags = {"imp": False, "clk": False}
        t_ref = [0.0]
        all_aids = []

        def on_req(req, _ad=ad_id, _f=flags, _t=t_ref, _aids=all_aids):
            u = req.url
            if 'doubleclick.net' not in u and 'dc_trk' not in u:
                return
            t = time.time() - _t[0] if _t[0] else 0
            # Capture any dc_trk_aid seen (for debugging)
            import re
            m = re.search(r'dc_trk_aid=(\d+)', u)
            if m and m.group(1) not in _aids:
                _aids.append(m.group(1))
                print(f"    [aid seen t+{t:.0f}s] {m.group(1)}")
            if _ad in u:
                if 'trackimp' in u and not _f["imp"]:
                    _f["imp"] = True; print(f"    [IMP t+{t:.0f}s] {u[:110]}")
                elif 'trackclk' in u and not _f["clk"]:
                    _f["clk"] = True; print(f"    [CLK t+{t:.0f}s] {u[:110]}")

        page.on("request", on_req)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3)
        click_consent(page)
        time.sleep(2)
        click_consent(page)

        # Scroll to trigger lazy-loaded ads
        for _ in range(8):
            try: page.evaluate("window.scrollBy(0, 300)")
            except: pass
            time.sleep(0.4)

        time.sleep(5)

        imp = flags["imp"]; clk = flags["clk"]
        if not imp:
            print("  [nothing yet, extra 10s wait]")
            time.sleep(10)
            imp = flags["imp"]; clk = flags["clk"]

        if imp and clk:     status = "PASS"
        elif imp:           status = "IMP ONLY"
        elif clk:           status = "CLK ONLY"
        else:               status = "NO TAG"

        print(f"  >> {status}")
        print(f"  All aids seen: {all_aids}")
        results.append((label, ad_id, status, imp, clk, all_aids[:]))
        page.close()

    ctx0.close()
    browser.close()

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for label, ad_id, status, imp, clk, aids in results:
    mark = "OK" if imp else "!!"
    print(f"  [{mark}] {label} | id={ad_id} | {status}")
    print(f"       all aids on page: {aids}")
