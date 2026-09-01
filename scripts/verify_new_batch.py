"""
New batch: HVP CB Minecraft&Stitch + BTS, Gazeta Screening
Campaign ID: 90000001
"""
from playwright.sync_api import sync_playwright
import time, sys

CAMPAIGN_ID = "90000001"
UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

HVP_ROWS = [
    ("CB Fullpage Minecraft&Stitch", "Desktop", "900000021",
     "https://kobieta.wp.pl/?wfName=280715_3084968_Retailclient_Kobieta_CBreak-MineCraft_Stitch_01&creName=desktop&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206488%2F1486101%2Fiaq%2FBaner_Commercial_Break%2F1694803%22%7D%5D&testPos=2"),
    ("CB Fullpage Minecraft&Stitch", "Mobile",  "900000021",
     "https://kobieta.wp.pl/?wfName=280715_3084968_Retailclient_Kobieta_CBreak-MineCraft_Stitch_01&creName=mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206488%2F1486101%2Fiaq%2FBaner_Commercial_Break%2F1694802%22%7D%5D&testPos=2"),
    ("CB Fullpage BTS",              "Desktop", "900000037",
     "https://kobieta.wp.pl/?wfName=280715_3084971_Retailclient_Kobieta_CBreak_BTS_01&creName=desktop&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206489%2F1486104%2Fiaq%2FBaner_Commercial_Break%2F1695026%22%7D%5D&testPos=2"),
    ("CB Fullpage BTS",              "Mobile",  "900000037",
     "https://kobieta.wp.pl/?wfName=280715_3084971_Retailclient_Kobieta_CBreak_BTS_01&creName=mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206489%2F1486104%2Fiaq%2FBaner_Commercial_Break%2F1694804%22%7D%5D&testPos=2"),
]

GAZETA_ROWS = [
    ("Screening 07.08 Minecraft&Stitch", "Desktop", "900000047",
     "https://kobieta.gazeta.pl/kobieta/0,0.html?google_preview=PLACEHOLDER&iu=90000005&gdfp_req=1&lineItemId=9000000612&creativeId=900000073741"),
    ("Screening 07.08 Minecraft&Stitch", "Mobile",  "900000047",
     "https://www.plotek.pl/plotek/0,0.html?google_preview=PLACEHOLDER&iu=90000005&gdfp_req=1&lineItemId=9000000612&creativeId=900000086211"),
    ("Screening 14.08 BTS",             "Desktop", "900000097",
     "https://www.edziecko.pl/edziecko/0,0.html?google_preview=PLACEHOLDER&iu=90000005&gdfp_req=1&lineItemId=9000001027&creativeId=900000110042"),
    ("Screening 14.08 BTS",             "Mobile",  "900000097",
     "https://www.chillizet.pl/?google_preview=PLACEHOLDER&iu=90000005&gdfp_req=1&lineItemId=9000001027&creativeId=900000089118"),
]

BAD_KW = ['premium','redakcja','regulamin','kontakt','/#','/tag/','testy-kons',
          '/wp-content','.jpg','.png','.css','.js','polityka','newsletter','rss','sitemap']

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

def make_listener(flags, t_ref, pid):
    def on_req(req, _f=flags, _t=t_ref, _pid=pid):
        u = req.url
        if 'doubleclick.net' not in u and 'dc_trk' not in u: return
        t = time.time() - _t[0] if _t[0] else 0
        pid_ok = _pid and _pid in u
        if 'trackimp' in u and not _f["imp"]:
            _f["imp"] = True; _f["imp_url"] = u[:180]
            print(f"    [IMP t+{t:.0f}s] {'PID_OK' if pid_ok else 'PID_MISS'} {u[35:120]}")
        elif 'trackclk' in u and not _f["clk"]:
            _f["clk"] = True
            print(f"    [CLK t+{t:.0f}s] {'PID_OK' if pid_ok else ''}")
    return on_req

def make_ctx(browser, device):
    mob = device == "Mobile"
    return browser.new_context(
        viewport={"width": 390, "height": 844} if mob else {"width": 1280, "height": 900},
        locale="pl-PL", user_agent=UA_M if mob else UA_D,
        ignore_https_errors=True
    )

log = open("new_batch_results.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d):
        for x in self.s:
            try: x.write(d)
            except: pass
    def flush(self):
        for x in self.s:
            try: x.flush()
            except: pass
sys.stdout = Tee(sys.__stdout__, log)

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # ── HVP Commercial Break ─────────────────────────────────────────────────────
    print("="*65)
    print("HVP Commercial Break — real Playwright click (isTrusted=true)")
    print("="*65)

    for fmt, device, pid, url in HVP_ROWS:
        print(f"\n[HVP] {fmt} | {device} | pid={pid}")
        ctx = make_ctx(browser, device)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid))

        try:
            page.goto(url, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"  [load warn] {e}")
            try: page.wait_for_load_state("domcontentloaded", timeout=5000)
            except: pass

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3); click_consent(page)
        time.sleep(2); click_consent(page)
        time.sleep(3)

        # Real Playwright click on visible article link
        clicked = False
        try:
            all_links = page.locator("a[href*='kobieta.wp.pl']")
            count = all_links.count()
            print(f"  [{count} links found]")

            for i in range(min(count, 40)):
                try:
                    link = all_links.nth(i)
                    href = link.get_attribute("href") or ""
                    path = href.replace("https://kobieta.wp.pl", "").replace("http://kobieta.wp.pl", "")
                    if len(path) < 15: continue
                    if any(b in href for b in BAD_KW): continue
                    if not link.is_visible(timeout=500): continue
                    print(f"  [clicking] {href[:80]}")
                    with page.expect_navigation(timeout=20000):
                        link.click()
                    print(f"  [navigated to article] -> {page.url[:70]}")
                    clicked = True
                    break
                except: continue

            if not clicked:
                # Scroll down and retry
                for _ in range(6):
                    page.evaluate("window.scrollBy(0, 400)")
                    time.sleep(0.4)
                for i in range(min(count, 60)):
                    try:
                        link = all_links.nth(i)
                        href = link.get_attribute("href") or ""
                        path = href.replace("https://kobieta.wp.pl", "")
                        if len(path) < 15: continue
                        if any(b in href for b in BAD_KW): continue
                        link.scroll_into_view_if_needed(timeout=3000)
                        time.sleep(0.3)
                        if link.is_visible(timeout=500):
                            print(f"  [clicking after scroll] {href[:80]}")
                            with page.expect_navigation(timeout=20000):
                                link.click()
                            print(f"  [navigated] -> {page.url[:70]}")
                            clicked = True
                            break
                    except: continue
        except Exception as e:
            print(f"  [click err] {e}")

        if not clicked:
            print("  [WARN] No article link clicked")

        # Wait on article page for CB impression
        time.sleep(25)

        imp = flags["imp"]; clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'} | clicked={clicked}")
        results.append(("HVP", fmt, device, pid, status, pid_c))
        page.close(); ctx.close()

    # ── Gazeta Screening ─────────────────────────────────────────────────────────
    print("\n" + "="*65)
    print("Gazeta Screening — GAM preview URLs")
    print("="*65)

    for fmt, device, pid, url in GAZETA_ROWS:
        print(f"\n[Gazeta] {fmt} | {device} | pid={pid}")
        ctx = make_ctx(browser, device)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [load warn] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3); click_consent(page)
        time.sleep(2); click_consent(page)

        # Scroll to trigger lazy-loaded ads
        for _ in range(4):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(0.5)

        time.sleep(20)

        imp = flags["imp"]; clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
        results.append(("Gazeta", fmt, device, pid, status, pid_c))
        page.close(); ctx.close()

    browser.close()

print("\n" + "="*65)
print("SUMMARY")
print("="*65)
for pub, fmt, dev, pid, status, pid_c in results:
    marker = "OK" if pid_c else "??"
    print(f"  [{status:<8}] {pub} | {fmt} | {dev} | pid={marker}")

try:
    log.close()
except: pass
