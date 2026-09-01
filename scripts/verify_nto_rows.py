"""Quick verify for nto.pl rows 38-39 (HPH PolskaPress Mobile)"""
from playwright.sync_api import sync_playwright
import re, time, sys

ROWS = [
    (38, "HPH", "PolskaPress image", "Mobile", "900000018",
     "https://nto.pl/niebo-nad-paczkowem-zaplonie-kolorami-znamy-program-xii-aeropikniku-i-balonowego-pucharu-polski/ar/c1p2-90000002?google_preview=PLACEHOLDER&iu=900000032&gdfp_req=1&lineItemId=9000000450&creativeId=900000057053"),
    (39, "HPH", "PolskaPress product", "Mobile", "900000060",
     "https://nto.pl/niebo-nad-paczkowem-zaplonie-kolorami-znamy-program-xii-aeropikniku-i-balonowego-pucharu-polski/ar/c1p2-90000002?google_preview=PLACEHOLDER&iu=900000032&gdfp_req=1&lineItemId=9000000450&creativeId=900000078085"),
]

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all',
               'Zgadzam się','Przejdź do serwisu','AKCEPTUJĘ']
    try:
        clicked = page.evaluate("""(phrases) => {
            for (const el of document.querySelectorAll('button, a')) {
                const t = (el.innerText || el.textContent || '').trim();
                if (phrases.some(p => t.toUpperCase() === p.toUpperCase() || t.toUpperCase().startsWith(p.toUpperCase()))) {
                    el.click(); return t;
                }
            }
            return null;
        }""", phrases)
        if clicked:
            print(f"    [consent] '{clicked}'")
            return True
    except:
        pass
    for sel in ["#onetrust-accept-btn-handler", ".fc-primary-button",
                "[class*='cmp-accept']", "[id*='accept']", ".cmp__btn--accept-all",
                "button[data-cmp-exp='acceptAll']"]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1000):
                el.click()
                print(f"    [consent-sel] {sel}")
                return True
        except:
            pass
    return False

def dom_scan(page, ad_id):
    found_imp = found_clk = False
    for frame in page.frames:
        try:
            res = frame.evaluate("""(id) => {
                const h = document.documentElement ? document.documentElement.outerHTML : '';
                const imp = new RegExp('trackimp[^"\'<>\\\\s]*dc_trk_aid=' + id, 'i').test(h)
                         || new RegExp('trackimpj[^"\'<>\\\\s]*dc_trk_aid=' + id, 'i').test(h);
                const clk = new RegExp('trackclk[^"\'<>\\\\s]*dc_trk_aid=' + id, 'i').test(h)
                         || new RegExp('trackclkns[^"\'<>\\\\s]*dc_trk_aid=' + id, 'i').test(h);
                return {imp, clk};
            }""", ad_id)
            if res['imp']: found_imp = True
            if res['clk']: found_clk = True
        except:
            pass
    return found_imp, found_clk

print("="*60)
print("HPH nto.pl rows 38-39")
print("="*60)

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    mobile_ua = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36")

    for row_i, publisher, fmt, device, ad_id, url in ROWS:
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844},
            locale="pl-PL",
            user_agent=mobile_ua,
            ignore_https_errors=True,
        )
        page = ctx.new_page()

        flags = {"imp": False, "clk": False}
        t_ref = [0.0]

        def on_req(req, _ad=ad_id, _f=flags, _t=t_ref):
            u = req.url
            if _ad not in u: return
            t = time.time() - _t[0] if _t[0] else 0
            if 'trackimp' in u and not _f["imp"]:
                _f["imp"] = True
                print(f"    [IMP NET t+{t:.0f}s] {u[:100]}")
            elif 'trackclk' in u and not _f["clk"]:
                _f["clk"] = True
                print(f"    [CLK NET t+{t:.0f}s] {u[:100]}")

        page.on("request", on_req)
        print(f"\n[row={row_i}] {publisher} | {fmt} | {device} | Ad ID={ad_id}")
        print(f"  URL: {url[:80]}...")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [load error] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(4)
        click_consent(page)
        time.sleep(3)
        click_consent(page)  # second attempt
        time.sleep(5)

        imp_net = flags["imp"]
        clk_net = flags["clk"]
        dom_imp, dom_clk = dom_scan(page, ad_id)
        if dom_imp and not imp_net:
            imp_net = True
            print(f"    [IMP DOM] dc_trk_aid={ad_id}")
        if dom_clk and not clk_net:
            clk_net = True
            print(f"    [CLK DOM] dc_trk_aid={ad_id}")

        if not imp_net and not clk_net:
            time.sleep(6)
            imp_net = imp_net or flags["imp"]
            clk_net = clk_net or flags["clk"]
            dom_imp2, dom_clk2 = dom_scan(page, ad_id)
            if dom_imp2 and not imp_net: imp_net = True; print(f"    [IMP DOM-2]")
            if dom_clk2 and not clk_net: clk_net = True; print(f"    [CLK DOM-2]")

        if imp_net and clk_net: status = "PASS"
        elif imp_net:           status = "IMP ONLY"
        elif clk_net:           status = "CLK ONLY"
        else:                   status = "NO TAG"

        print(f"  >> {status}")
        results.append((row_i, publisher, fmt, device, ad_id, status))
        page.close()
        ctx.close()

    browser.close()

print("\nSUMMARY nto.pl rows:")
for r in results:
    print(f"  [{r[5]}] row={r[0]} | {r[1]} | {r[3]} | id={r[4]}")
