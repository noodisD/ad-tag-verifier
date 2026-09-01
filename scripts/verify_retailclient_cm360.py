"""
CM360 tag verification — Retailclient CDR P36-P37 Ladies Palm Beach
Checks: ad.doubleclick.net/ddm/trackimp (impression) + trackclk (click)
Identified by dc_trk_aid=AD_ID
"""
from playwright.sync_api import sync_playwright
import re, time, sys

# (label, is_mobile, expected_ad_id, url, needs_article_click)
TEST_URLS = [
    # HVP Commercial Break — fires after clicking into article
    ("HVP CB XL1 desktop",   False, 900000016, "https://kobieta.wp.pl/?wfName=276974_3074575_Retailclient-L1_Kobieta_CBFull_01&creName=desktop&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200827%2F1460968%2Fiaq%2FBaner_Commercial_Break%2F1584942%22%7D%5D&testPos=2", True),
    ("HVP CB XL1 mobile",    True,  900000016, "https://kobieta.wp.pl/?wfName=276974_3074575_Retailclient-L1_Kobieta_CBFull_01&creName=mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200827%2F1460968%2Fiaq%2FBaner_Commercial_Break%2F1584943%22%7D%5D&testPos=2", True),
    ("HVP CB XL2 desktop",   False, 900000029, "https://kobieta.wp.pl/?wfName=276974_3074589_Retailclient-L2_Kobieta_CBFull_01&creName=desktop&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200828%2F1460971%2Fiaq%2FBaner_Commercial_Break%2F1584945%22%7D%5D&testPos=2", True),
    ("HVP CB XL2 mobile",    True,  900000029, "https://kobieta.wp.pl/?wfName=276974_3074589_Retailclient-L2_Kobieta_CBFull_01&creName=mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200828%2F1460971%2Fiaq%2FBaner_Commercial_Break%2F1584946%22%7D%5D&testPos=2", True),
    # PushAd
    ("PushAd Push 1",        False, 900000031, "https://app2.push-ad.com/preview/25b042759d4f5e689ddec788f1a7f9000000467aac7ab900000050c9b1fc4f0a", False),
    ("PushAd Push 2",        False, 900000031, "https://app2.push-ad.com/preview/bf667c45c1b4ef6f4408bcd31de6e887fe75ccb77ddf6e3cbcf94175b6d29acb", False),
    # Adquery
    ("Adquery Richmedia",    False, 900000019, "https://backend.adquery.io/preview/Mjk5MTQ=", False),
    # RASP
    ("RASP BIM2 D screening",False, 900000065, "https://kobieta.onet.pl/#adbeta=r147304!slot.top", False),
    ("RASP BIM2 M rect L1",  True,  900000065, "https://kobieta.onet.pl/?ress=mobile#adbeta=r147305!slot.top", False),
    ("RASP BIM2 M rect L2",  True,  900000065, "https://kobieta.onet.pl/?ress=mobile#adbeta=r147307!slot.top", False),
    # Social — attempt load, likely needs login
    ("TikTok",               True,  900000062, "https://v-ttam.tiktok.com/s/ZSxvTAhCQ/", False),
    ("Meta CPM Collection",  False, 900000013, "https://fb.me/adspreview/facebook/1P0m4l7gyBqDrwp", False),
    ("Meta CPM Carousel",    False, 900000013, "https://fb.me/adspreview/facebook/1TxQVCGbmlKyKcd", False),
    ("Meta CPM PhotoLink",   False, 900000013, "https://fb.me/adspreview/facebook/2e0gSqbLokHOXs6", False),
    ("Meta RTG Collection",  False, 900000070, "https://fb.me/adspreview/facebook/2aqfCccnTYOVZ4W", False),
    ("Meta RTG Carousel",    False, 900000070, "https://fb.me/adspreview/facebook/2ks89fnyLgyh3Z7", False),
    ("Meta RTG PhotoLink",   False, 900000070, "https://fb.me/adspreview/facebook/263b3kPZ4dkYl1m", False),
]

CONSENT_SELECTORS = [
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj wszystko')",
    "button:has-text('Akceptuj')", "button:has-text('Akceptuję')",
    "button:has-text('Zgadzam się')", "button:has-text('Accept all')",
    "#onetrust-accept-btn-handler", ".js-accept-all", "[class*='accept-all']",
    "button[data-cy='accept-all']", "[class*='agree']", "[class*='accept']",
    "button.sp_choice_type_11",
]

def extract_aid(url):
    m = re.search(r'dc_trk_aid=(\d+)', url)
    return int(m.group(1)) if m else None

def click_consent(page):
    # JS approach first
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj wszystko',
                             'Akceptuj','Zgadzam się','Accept all','Accept'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked:
            print(f"    [consent-js] '{clicked}'")
            return True
    except: pass
    # Playwright locators fallback
    for sel in CONSENT_SELECTORS:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click()
                print(f"    [consent] {sel}")
                return True
        except: pass
    for frame in page.frames:
        if frame == page.main_frame: continue
        try:
            clicked = frame.evaluate("""() => {
                const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Zgadzam się','Accept all'];
                for (const b of document.querySelectorAll('button')) {
                    const t = b.innerText.trim();
                    if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
                }
                return null;
            }""")
            if clicked:
                print(f"    [consent-iframe-js] '{clicked}'")
                return True
        except: pass
    return False

def setup_consent(ctx, url):
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.bring_to_front()
        time.sleep(7)
        if click_consent(page):
            time.sleep(2)
            print(f"  [consent-setup] done — {url[:60]}")
        else:
            print(f"  [consent-setup] no popup — {url[:60]}")
    except Exception as e:
        print(f"  [consent-setup] error: {e}")
    finally:
        page.close()

def get_click_aids_from_dom(page):
    """Find dc_trk_aid= in trackclk URLs across all frames"""
    found = set()
    for frame in page.frames:
        try:
            aids = frame.evaluate(r"""() => {
                const aids = new Set();
                const re = /trackclk[^"'\s]*dc_trk_aid=(\d+)/gi;
                document.querySelectorAll('[href],[src],[onclick]').forEach(el => {
                    ['href','src','onclick'].forEach(a => {
                        const v = decodeURIComponent(el.getAttribute(a) || '');
                        const m = v.match(re);
                        if (m) m.forEach(x => { const n = x.match(/dc_trk_aid=(\d+)/); if(n) aids.add(parseInt(n[1])); });
                    });
                });
                document.querySelectorAll('a').forEach(a => {
                    const h = decodeURIComponent(a.href || '');
                    if (h.includes('trackclk')) {
                        const n = h.match(/dc_trk_aid=(\d+)/);
                        if (n) aids.add(parseInt(n[1]));
                    }
                });
                document.querySelectorAll('script').forEach(s => {
                    const matches = s.textContent.matchAll(/trackclk[^"'\s]*dc_trk_aid=(\d+)/g);
                    for (const m of matches) aids.add(parseInt(m[1]));
                });
                return [...aids];
            }""")
            for a in aids:
                found.add(a)
        except: pass
    return found

def check_url(ctx, label, expected_aid, url, needs_article_click=False):
    imp_aids = []
    t_ref = [0.0]

    def on_req(req):
        u = req.url
        t = time.time() - t_ref[0] if t_ref[0] else 0
        if 'doubleclick.net/ddm/trackimp' in u:
            aid = extract_aid(u)
            if aid and aid not in imp_aids:
                imp_aids.append(aid)
                print(f"    [IMP] dc_trk_aid={aid}  t+{t:.1f}s")
        elif 'doubleclick.net/ddm/trackclk' in u:
            aid = extract_aid(u)
            if aid:
                print(f"    [CLK-net] dc_trk_aid={aid}  t+{t:.1f}s")

    page = ctx.new_page()
    page.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [load error] {e}")

    t_ref[0] = time.time()
    page.bring_to_front()

    if click_consent(page):
        try: page.wait_for_load_state("domcontentloaded", timeout=8000)
        except: pass
        t_ref[0] = time.time()
        imp_aids.clear()

    time.sleep(2)

    # For Commercial Break: click first article link to trigger the format
    if needs_article_click:
        try:
            # Find first article link on the page — must be kobieta.wp.pl content, not login/mail
            article_link = page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                const BAD = ['login', 'poczta', 'mailto', 'javascript', 'account', 'rejestracja',
                             'logowanie', '#', 'facebook', 'twitter', 'instagram'];
                function isBad(h) { return BAD.some(b => h.toLowerCase().includes(b)); }
                // Priority: article patterns within kobieta.wp.pl
                for (const a of links) {
                    const h = a.href;
                    if (!h.includes('kobieta.wp.pl')) continue;
                    if (isBad(h)) continue;
                    if (h.includes('/artykul/') || h.includes('/news/') ||
                        h.includes('/wiadomosci/') || h.includes('/styl/') ||
                        h.includes('/zdrowie/') || h.includes('/uroda/') ||
                        h.includes('/zycie/') || h.includes('/dieta/')) {
                        return h;
                    }
                }
                // Fallback: any kobieta.wp.pl path that looks like content (has slug-like path)
                for (const a of links) {
                    const h = a.href;
                    if (!h.includes('kobieta.wp.pl')) continue;
                    if (isBad(h)) continue;
                    const path = new URL(h).pathname;
                    if (path.length > 5 && path !== '/') return h;
                }
                return null;
            }""")
            if article_link:
                print(f"    [article-click] {article_link[:80]}")
                page.goto(article_link, wait_until="domcontentloaded", timeout=20000)
                t_ref[0] = time.time()
                imp_aids.clear()
                time.sleep(2)
        except Exception as e:
            print(f"    [article-click error] {e}")

    # Scroll
    for _ in range(80):
        if imp_aids:
            time.sleep(2)
            break
        try:
            page_h = page.evaluate("document.body.scrollHeight") or 20000
            cur = page.evaluate("window.pageYOffset + document.documentElement.clientHeight") or 0
            if cur >= page_h: break
            page.evaluate("window.scrollBy(0, 300)")
        except: pass
        time.sleep(1.2)

    time.sleep(2)

    # DOM scan for click tags
    clk_aids = get_click_aids_from_dom(page)
    for a in clk_aids:
        print(f"    [DOM-CLK] dc_trk_aid={a}")

    page.close()

    imp_unique = list(set(imp_aids))
    clk_unique = sorted(clk_aids)

    imp_ok = expected_aid in imp_unique
    clk_ok = expected_aid in clk_aids

    if imp_ok and clk_ok:
        status = "[PASS]"
    elif imp_ok:
        status = "[IMP OK / CLICK MISSING]"
    elif imp_unique or clk_unique:
        status = f"[FAIL - wrong aid: imp={imp_unique} clk={clk_unique}]"
    else:
        status = "[NO TAG FIRED]"

    print(f"  Status   : {status}")
    print(f"  Expected : dc_trk_aid={expected_aid}")
    print(f"  IMP aids : {imp_unique or 'none'}")
    print(f"  CLK aids : {clk_unique or 'none'}")
    return status, imp_unique, clk_unique


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
        setup_consent(desktop_ctx, "https://kobieta.wp.pl/")
        setup_consent(mobile_ctx,  "https://kobieta.wp.pl/")
        setup_consent(desktop_ctx, "https://kobieta.onet.pl/")
        setup_consent(mobile_ctx,  "https://kobieta.onet.pl/?ress=mobile")

        results = []
        print("\n" + "="*60)
        print("Retailclient CDR — CM360 tag verification")
        print("="*60)

        for label, is_mobile, expected_aid, url, needs_click in TEST_URLS:
            ctx = mobile_ctx if is_mobile else desktop_ctx
            print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")
            status, imp, clk = check_url(ctx, label, expected_aid, url, needs_click)
            results.append((label, expected_aid, status, imp, clk))

        browser.close()

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for label, aid, status, imp, clk in results:
            print(f"  {status:<40} aid={aid}  {label}")

        passed = sum(1 for *_, s, i, c in results if s == "[PASS]")
        imp_ok = sum(1 for *_, s, i, c in results if i)
        total  = len(results)
        print(f"\n{passed}/{total} fully verified (impression + click)")
        print(f"{imp_ok}/{total} impressions OK")


if __name__ == "__main__":
    log = open("retailclient_cm360_results.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
