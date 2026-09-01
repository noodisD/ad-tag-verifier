"""
HVP CB retest — fresh context per test + real click (not goto) on article link
"""
from playwright.sync_api import sync_playwright
import re, time, sys

TEST_URLS = [
    ("HVP CB XL1 desktop", False, 900000016, "https://kobieta.wp.pl/?wfName=276974_3074575_Retailclient-L1_Kobieta_CBFull_01&creName=desktop&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200827%2F1460968%2Fiaq%2FBaner_Commercial_Break%2F1584942%22%7D%5D&testPos=2"),
    ("HVP CB XL1 mobile",  True,  900000016, "https://kobieta.wp.pl/?wfName=276974_3074575_Retailclient-L1_Kobieta_CBFull_01&creName=mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200827%2F1460968%2Fiaq%2FBaner_Commercial_Break%2F1584943%22%7D%5D&testPos=2"),
    ("HVP CB XL2 desktop", False, 900000029, "https://kobieta.wp.pl/?wfName=276974_3074589_Retailclient-L2_Kobieta_CBFull_01&creName=desktop&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200828%2F1460971%2Fiaq%2FBaner_Commercial_Break%2F1584945%22%7D%5D&testPos=2"),
    ("HVP CB XL2 mobile",  True,  900000029, "https://kobieta.wp.pl/?wfName=276974_3074589_Retailclient-L2_Kobieta_CBFull_01&creName=mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22200828%2F1460971%2Fiaq%2FBaner_Commercial_Break%2F1584946%22%7D%5D&testPos=2"),
]

log = open("hvp_click_retest.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

def extract_aid(url):
    m = re.search(r'dc_trk_aid=(\d+)', url)
    return int(m.group(1)) if m else None

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję i przechodzę do serwisu','Akceptuję','Akceptuj wszystkie',
                             'Akceptuj wszystko','Akceptuj','Zgadzam się','Accept all'];
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
                print(f"    [consent-iframe] '{clicked}'")
                return True
        except: pass
    return False

def get_click_aids_from_dom(page):
    found = set()
    for frame in page.frames:
        try:
            aids = frame.evaluate(r"""() => {
                const aids = new Set();
                document.querySelectorAll('[href],[src],[onclick]').forEach(el => {
                    ['href','src','onclick'].forEach(a => {
                        const v = decodeURIComponent(el.getAttribute(a) || '');
                        if (v.includes('trackclk')) {
                            const n = v.match(/dc_trk_aid=(\d+)/);
                            if (n) aids.add(parseInt(n[1]));
                        }
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
                    const ms = s.textContent.matchAll(/trackclk[^"'\s]*dc_trk_aid=(\d+)/g);
                    for (const m of ms) aids.add(parseInt(m[1]));
                });
                return [...aids];
            }""")
            for a in aids: found.add(a)
        except: pass
    return found

def check_url(browser, label, is_mobile, expected_aid, url):
    imp_aids = []
    all_aids = []  # capture everything that fires
    t_ref = [0.0]

    def on_req(req):
        u = req.url
        t = time.time() - t_ref[0] if t_ref[0] else 0
        if 'doubleclick.net/ddm/trackimp' in u:
            aid = extract_aid(u)
            if aid:
                all_aids.append(aid)
                if aid not in imp_aids:
                    imp_aids.append(aid)
                    print(f"    [IMP] dc_trk_aid={aid}  t+{t:.1f}s")
        elif 'doubleclick.net/ddm/trackclk' in u:
            aid = extract_aid(u)
            if aid:
                print(f"    [CLK-net] dc_trk_aid={aid}  t+{t:.1f}s")

    # Fresh context for every single test — kills frequency cap
    if is_mobile:
        ctx = browser.new_context(
            viewport={"width": 390, "height": 844}, locale="pl-PL",
            user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
        )
    else:
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="pl-PL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

    page = ctx.new_page()
    page.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [load error] {e}")

    t_ref[0] = time.time()
    page.bring_to_front()
    time.sleep(8)  # wait for CMP popup to render

    if click_consent(page):
        try: page.wait_for_load_state("domcontentloaded", timeout=8000)
        except: pass
        time.sleep(3)
        t_ref[0] = time.time()
        imp_aids.clear()
        all_aids.clear()
    else:
        print(f"    [consent] no popup found — continuing anyway")

    time.sleep(3)

    # Find article link and CLICK it (not goto) to preserve the CB click-trigger
    try:
        article_href = page.evaluate("""() => {
            const BAD = ['login','poczta','mailto','javascript','account','rejestracja',
                         'logowanie','facebook','twitter','instagram'];
            function isBad(h) { return BAD.some(b => h.toLowerCase().includes(b)); }
            const links = document.querySelectorAll('a[href]');
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
            for (const a of links) {
                const h = a.href;
                if (!h.includes('kobieta.wp.pl')) continue;
                if (isBad(h)) continue;
                try {
                    const path = new URL(h).pathname;
                    if (path.length > 5 && path !== '/') return h;
                } catch(e) {}
            }
            return null;
        }""")

        if article_href:
            print(f"    [article-click] {article_href[:100]}")
            # Use real click — triggers CB format the same way a user would
            with page.expect_navigation(timeout=15000):
                page.evaluate(f"""() => {{
                    const a = document.querySelector('a[href="{article_href}"]') ||
                              [...document.querySelectorAll('a')].find(x => x.href === '{article_href}');
                    if (a) a.click();
                }}""")
            t_ref[0] = time.time()
            imp_aids.clear()
            all_aids.clear()
            time.sleep(3)
        else:
            print(f"    [article-click] no article link found")
    except Exception as e:
        print(f"    [article-click error] {e}")

    # Scroll to let CB animate/fire
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

    clk_aids = get_click_aids_from_dom(page)
    for a in clk_aids:
        print(f"    [DOM-CLK] dc_trk_aid={a}")

    ctx.close()

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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    results = []
    print("\n" + "="*60)
    print("HVP CB — fresh context + real click retest")
    print("="*60)

    for label, is_mobile, expected_aid, url in TEST_URLS:
        print(f"\n[{label}]  {'[mobile]' if is_mobile else '[desktop]'}")
        status, imp, clk = check_url(browser, label, is_mobile, expected_aid, url)
        results.append((label, expected_aid, status, imp, clk))

    browser.close()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for label, aid, status, imp, clk in results:
        print(f"  {status:<40} aid={aid}  {label}")

    passed = sum(1 for *_, s, i, c in results if s == "[PASS]")
    print(f"\n{passed}/{len(results)} fully verified (impression + click)")

log.close()
