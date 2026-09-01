"""
Targeted recheck for rows 26, 28 (Gazeta Mobile) and 38, 39 (nto.pl Mobile).
Rows 26/28 failed in v1 because they used a shared desktop context.
Rows 38/39: investigate what actually fires on nto.pl.
"""
from playwright.sync_api import sync_playwright
import re, time, sys

UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

ROWS = [
    (26, "Gazeta", "KOBIETA TOPBOARD MAX SCREENING 17.07", "Mobile", "900000011",
     "https://kobieta.gazeta.pl/kobieta/0,0.html?google_preview=PLACEHOLDER&iu=90000002&gdfp_req=1&lineItemId=9000000363&creativeId=900000043021"),
    (28, "Gazeta", "KOBIETA TOPBOARD MAX SCREENING 20.07", "Mobile", "900000057",
     "https://kobieta.gazeta.pl/kobieta/0,0.html?google_preview=PLACEHOLDER&iu=90000002&gdfp_req=1&lineItemId=9000000683&creativeId=900000077132"),
    (38, "HPH", "PolskaPress image", "Mobile", "900000088",
     "https://nto.pl/niebo-nad-paczkowem-zaplonie-kolorami-znamy-program-xii-aeropikniku-i-balonowego-pucharu-polski/ar/c1p2-90000009?google_preview=PLACEHOLDER&iu=900000102&gdfp_req=1&lineItemId=9000001150&creativeId=900000127053"),
    (39, "HPH", "PolskaPress product", "Mobile", "900000130",
     "https://nto.pl/niebo-nad-paczkowem-zaplonie-kolorami-znamy-program-xii-aeropikniku-i-balonowego-pucharu-polski/ar/c1p2-90000009?google_preview=PLACEHOLDER&iu=900000102&gdfp_req=1&lineItemId=9000001150&creativeId=900000148085"),
]

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all','AKCEPTUJĘ']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t = (el.innerText||el.textContent||'').trim().toUpperCase();
                if (p.some(x => t===x.toUpperCase()||t.startsWith(x.toUpperCase()))) {el.click();return t;}
            } return null;
        }""", phrases)
        if ok: print(f"    [consent] {ok}"); return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']",
                ".cmp__btn--accept-all","[class*='consent-accept']","[class*='accept-all']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); print(f"    [consent-sel] {sel}"); return True
        except: pass
    return False

print("="*60)
print("Targeted recheck: Gazeta Mobile + nto.pl")
print("="*60)

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # Consent warmup for each domain
    for site, mob in [("https://kobieta.gazeta.pl/", True), ("https://nto.pl/", True)]:
        ctx = browser.new_context(viewport={"width":390,"height":844}, locale="pl-PL",
                                  user_agent=UA_M, ignore_https_errors=True)
        pg = ctx.new_page()
        pg.goto(site, wait_until="domcontentloaded", timeout=20000)
        pg.bring_to_front(); time.sleep(6)
        ok = click_consent(pg); time.sleep(2)
        print(f"  warmup {site} consent={ok}")
        pg.close()
        ctx.close()

    for row_i, publisher, fmt, device, ad_id, url in ROWS:
        ctx = browser.new_context(viewport={"width":390,"height":844}, locale="pl-PL",
                                  user_agent=UA_M, ignore_https_errors=True)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False}
        all_bns = []
        t_ref = [0.0]

        def on_req(req, _ad=ad_id, _f=flags, _t=t_ref, _b=all_bns):
            u = req.url
            t = time.time() - _t[0] if _t[0] else 0
            if _ad in u:
                if 'trackimp' in u and not _f["imp"]:
                    _f["imp"] = True
                    print(f"    [IMP t+{t:.0f}s] {u[:110]}")
                elif 'trackclk' in u and not _f["clk"]:
                    _f["clk"] = True
                    print(f"    [CLK t+{t:.0f}s] {u[:110]}")
            # Capture ALL doubleclick requests for debugging
            if 'doubleclick.net' in u or 'dc_trk' in u:
                m = re.search(r'dc_trk_aid=(\d+)', u)
                if m and m.group(1) not in _b:
                    _b.append(m.group(1))
                    print(f"    [debug t+{t:.0f}s] aid={m.group(1)} {u[:80]}")

        page.on("request", on_req)
        print(f"\n[row={row_i}] {publisher} | {fmt} | id={ad_id}")
        print(f"  URL: {url[:80]}...")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(4)
        click_consent(page)
        time.sleep(2)
        click_consent(page)  # second attempt
        time.sleep(6)

        imp = flags["imp"]
        clk = flags["clk"]

        if not imp and not clk:
            print(f"  [nothing yet, extra 8s wait]")
            time.sleep(8)
            imp = flags["imp"]; clk = flags["clk"]

        if imp and clk:   status = "PASS"
        elif imp:         status = "IMP ONLY"
        elif clk:         status = "CLK ONLY"
        else:             status = "NO TAG"

        print(f"  >> {status}")
        if not imp and not clk:
            print(f"  >> All aids seen: {all_bns[:10]}")
        results.append((row_i, publisher, device, ad_id, status))

        page.close()
        ctx.close()

    browser.close()

print("\nSUMMARY:")
for r in results:
    print(f"  [{r[4]}] row={r[0]} | {r[1]} | {r[2]} | id={r[3]}")
