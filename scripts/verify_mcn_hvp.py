"""
MCN (45s wait) + HVP Commercial Break (click article to trigger inter-page ad)
"""
from playwright.sync_api import sync_playwright
import re, time, sys

CAMPAIGN_ID = "90000001"

MCN_ROWS = [
    ("MCN", "L-frame FC Barcelona", "Desktop", "900000022", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjEvMzgw?position=horizontal&template=ecommerce"),
    ("MCN", "L-frame Bekkin",       "Desktop", "900000039", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjIvMzgx?position=horizontal&template=ecommerce"),
    ("MCN", "L-frame Clothing",     "Desktop", "900000042", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjMvMzgy?position=horizontal&template=ecommerce"),
]

HVP_ROWS = [
    ("HVP", "CB XL mobile",   "Mobile",  "900000052", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_1_desktop_clothing&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690209%22%7D%5D&testPos=2"),
    ("HVP", "CB XL Clothing", "Desktop", "900000067", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_2_desktop_bekkin&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690210%22%7D%5D&testPos=2"),
    ("HVP", "CB XL Bekkin",   "Desktop", "900000078", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_3_desktop_barcelona&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690211%22%7D%5D&testPos=2"),
    ("HVP", "CB XL FC Barca", "Desktop", "900000084", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=360x600_mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484054%2Fiaq%2FBaner_Commercial_Break%2F1690208%22%7D%5D&testPos=2"),
]

UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

def make_ctx(browser, device):
    mob = device == "Mobile"
    return browser.new_context(
        viewport={"width": 390, "height": 844} if mob else {"width": 1280, "height": 900},
        locale="pl-PL", user_agent=UA_M if mob else UA_D, ignore_https_errors=True)

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all','AKCEPTUJĘ','Przejdź do serwisu']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t=(el.innerText||el.textContent||'').trim().toUpperCase();
                if(p.some(x=>t===x.toUpperCase()||t.startsWith(x.toUpperCase()))){el.click();return t;}
            } return null;
        }""", phrases)
        if ok: return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']",".cmp__btn--accept-all"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); return True
        except: pass
    return False

def make_listener(flags, t_ref, placement_id):
    def on_req(req, _f=flags, _t=t_ref, _pid=placement_id):
        u = req.url
        if 'doubleclick.net' not in u and 'dc_trk' not in u: return
        t = time.time() - _t[0] if _t[0] else 0
        pid_ok = _pid and _pid in u
        if 'trackimp' in u and not _f["imp"] and (pid_ok or not _pid):
            _f["imp"] = True; _f["imp_url"] = u[:160]
            print(f"    [IMP t+{t:.0f}s] {'PID_OK' if pid_ok else 'no_pid'} {u[35:110]}")
        elif 'trackclk' in u and not _f["clk"] and (pid_ok or not _pid):
            _f["clk"] = True
            print(f"    [CLK t+{t:.0f}s]")
    return on_req

log = open("mcn_hvp_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d):
        for x in self.s:
            try: x.write(d)
            except: pass
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # ── MCN ─────────────────────────────────────────────────────────────────────
    print("="*60)
    print("MCN L-frame — 45s wait per row")
    print("="*60)
    for publisher, fmt, device, pid, url in MCN_ROWS:
        print(f"\n[{publisher}] {fmt} | pid={pid}")
        ctx = make_ctx(browser, device)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [load err] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3); click_consent(page); time.sleep(2)
        try: page.mouse.click(640, 400)
        except: pass
        time.sleep(45)

        imp = flags["imp"]; clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
        results.append((publisher, fmt, device, pid, status, pid_c))
        page.close(); ctx.close()

    # ── HVP Commercial Break ─────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("HVP Commercial Break — load URL, then click article to trigger")
    print("="*60)

    for publisher, fmt, device, pid, url in HVP_ROWS:
        mob = device == "Mobile"
        print(f"\n[{publisher}] {fmt} | {device} | pid={pid}")
        ctx = make_ctx(browser, device)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [load err] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3); click_consent(page); time.sleep(3)

        # Find and click an article link to trigger Commercial Break between pages
        print("  [clicking article link to trigger Commercial Break...]")
        clicked_article = False
        try:
            # Try to find article links (WP kobieta articles)
            article_url = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                for (const a of links) {
                    const h = a.href;
                    if (h.includes('kobieta.wp.pl') && !h.includes('?') && h.length > 35
                        && !h.endsWith('.pl/') && !h.includes('#')
                        && (h.includes('/artykul/') || h.includes(',') || h.match(/\\/\\d+,/))) {
                        return h;
                    }
                }
                // Fallback: any internal wp.pl link
                for (const a of links) {
                    const h = a.href;
                    if (h.includes('kobieta.wp.pl') && h.length > 40) return h;
                }
                return null;
            }""")
            if article_url:
                print(f"  [navigating to] {article_url[:80]}")
                page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
                clicked_article = True
            else:
                print("  [no article link found, trying mouse click on headline]")
                page.mouse.click(640 if not mob else 195, 400)
        except Exception as e:
            print(f"  [article click err] {e}")

        time.sleep(15)

        if not flags["imp"] and not clicked_article:
            # Try scrolling and clicking a visible link
            for _ in range(5):
                try: page.evaluate("window.scrollBy(0, 300)")
                except: pass
                time.sleep(0.5)
            time.sleep(5)

        imp = flags["imp"]; clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
        results.append((publisher, fmt, device, pid, status, pid_c))
        page.close(); ctx.close()

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for pub, fmt, dev, pid, status, pid_c in results:
    print(f"  [{status:<8}] {pub} | {fmt} | {dev} | pid={'OK' if pid_c else '??'}")

log.close()
