"""
New batch — IMP + CLK verification (v7 FINAL)
HVP CB:  expect_request(trackimp) → click CB → CLK confirmed if popup→retailclient.pl
         (WP CB uses direct URL + UTM, no standard CM360 trackclk)
Gazeta:  poll flags["imp"] → popup click → 60s wait → CM360 trackclk fires ~54s
Campaign: 90000001
"""
from playwright.sync_api import sync_playwright
import time, sys, os

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
            _f["clk"] = True; _f["clk_url"] = u[:180]
            print(f"    [CLK t+{t:.0f}s] {'PID_OK' if pid_ok else 'PID_MISS'} {u[35:120]}")
    return on_req

def make_ctx(browser, device):
    mob = device == "Mobile"
    return browser.new_context(
        viewport={"width": 390, "height": 844} if mob else {"width": 1280, "height": 900},
        locale="pl-PL", user_agent=UA_M if mob else UA_D,
        ignore_https_errors=True
    )

def click_cb(page, vp_w, vp_h, flags, t_ref, pid):
    """Click CB creative. WP CB opens retailclient.pl directly (no CM360 trackclk).
    CLK is confirmed when popup URL contains 'retailclient'.
    """
    desktop = vp_w > 500
    # Positions ordered by likelihood of hitting the ad (CTA button first, then center areas)
    positions = [
        (int(vp_w * 0.86), int(vp_h * 0.76)) if desktop else (int(vp_w * 0.72), int(vp_h * 0.83)),
        (vp_w // 2, int(vp_h * 0.50)),
        (vp_w // 2, int(vp_h * 0.35)),
        (int(vp_w * 0.75), int(vp_h * 0.55)),
        (vp_w // 2, int(vp_h * 0.65)),
    ]
    for x, y in positions:
        try:
            with page.expect_popup(timeout=2000) as pup:
                page.mouse.click(x, y)
            popup = pup.value
            popup.on("request", make_listener(flags, t_ref, pid))
            popup_url = popup.url
            time.sleep(2)
            popup_url = popup.url  # refresh after brief wait
            print(f"    [popup ({x},{y}): {popup_url[:80]}]")
            # WP CB CLK confirmation: popup goes to retailclient.pl with CM360 UTM
            if 'retailclient' in popup_url.lower():
                if not flags["clk"]:
                    flags["clk"] = True
                    flags["clk_url"] = popup_url[:180]
                    t = time.time() - t_ref[0]
                    print(f"    [CLK via retailclient popup t+{t:.0f}s] {popup_url[:100]}")
                return True
        except:
            time.sleep(0.5)
            if flags["clk"]: return True
    print("    [no popup opened from CB]")
    return False

def click_ad_frame(page, vp_w, vp_h, flags, t_ref, pid):
    """Find ad link in non-main frames and click. For Gazeta Screening.
    CM360 trackclk fires ~47-54s after t_ref via adclick.g.doubleclick.net redirect chain.
    """
    main_url = page.url.split("?")[0]
    for frame in page.frames:
        if frame.url and frame.url.split("?")[0] == main_url: continue
        try:
            locs = [
                frame.locator("a[href*='ddm/trackclk']"),
                frame.locator("a[href*='adclick.g.doubleclick']"),
                frame.locator("a[href*='doubleclick.net']"),
            ]
            for loc in locs:
                n = loc.count()
                if n == 0: continue
                href = loc.first.get_attribute("href") or ""
                print(f"    [ad link in frame {frame.url[:50]}] {href[:80]}")
                try:
                    with page.expect_popup(timeout=4000) as popup_info:
                        loc.first.click()
                    popup = popup_info.value
                    popup.on("request", make_listener(flags, t_ref, pid))
                    # CLK fires ~90s after popup opens; wait 120s
                    time.sleep(120)
                    print(f"    [popup final url: {popup.url[:70]}]")
                    return True
                except:
                    time.sleep(10)
                    return True
        except: continue

    print("    [no ad link in non-main frames — mouse fallback]")
    for x, y in [(vp_w // 2, 150), (vp_w // 2, vp_h // 2)]:
        try: page.mouse.click(x, y)
        except: pass
        time.sleep(0.5)
    return False

log = open("new_batch_clk_results.txt", "w", encoding="utf-8", buffering=1)
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
    print("HVP CB — IMP via trackimp | CLK via retailclient popup (WP CB format)")
    print("="*65)

    for fmt, device, pid, url in HVP_ROWS:
        mob = device == "Mobile"
        vp_w = 390 if mob else 1280
        vp_h = 844 if mob else 900
        print(f"\n[HVP] {fmt} | {device} | pid={pid}")

        ctx = make_ctx(browser, device)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": "", "clk_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid))
        ctx.on("page", lambda np, _f=flags, _t=t_ref, _pid=pid:
               np.on("request", make_listener(_f, _t, _pid)))

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

        article_link = None
        try:
            all_links = page.locator("a[href*='kobieta.wp.pl']")
            for i in range(min(all_links.count(), 40)):
                try:
                    link = all_links.nth(i)
                    href = link.get_attribute("href") or ""
                    if len(href.replace("https://kobieta.wp.pl","")) < 15: continue
                    if any(b in href for b in BAD_KW): continue
                    if not link.is_visible(timeout=500): continue
                    article_link = link
                    print(f"  [article] {href[:75]}")
                    break
                except: continue
        except: pass

        if article_link:
            try:
                with page.expect_request(
                    lambda r: "trackimp" in r.url and pid in r.url,
                    timeout=60000
                ):
                    article_link.click()

                t_now = time.time() - t_ref[0]
                print(f"  [IMP confirmed at t+{t_now:.0f}s — clicking CB]")
                time.sleep(1)
                click_cb(page, vp_w, vp_h, flags, t_ref, pid)
                time.sleep(3)

            except Exception as e:
                print(f"  [expect_request err] {e}")
        else:
            print("  [no article link found]")

        imp = flags["imp"]; clk = flags["clk"]
        pid_imp = pid in flags["imp_url"] if flags["imp_url"] else False
        pid_clk = "retailclient" in flags["clk_url"].lower() if flags["clk_url"] else (pid in flags["clk_url"] if flags["clk_url"] else False)
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        clk_note = "(retailclient popup)" if clk and "retailclient" in flags["clk_url"].lower() else "(trackclk)"
        print(f"  >> {status} | imp={'OK' if pid_imp else 'NO'} clk={'OK' if clk else 'NO'} {clk_note if clk else ''}")
        results.append(("HVP", fmt, device, pid, status, pid_imp, clk, flags["clk_url"]))
        page.close(); ctx.close()

    # ── Gazeta Screening ─────────────────────────────────────────────────────────
    print("\n" + "="*65)
    print("Gazeta Screening — CM360 trackclk via adclick popup (~54s)")
    print("="*65)

    for fmt, device, pid, url in GAZETA_ROWS:
        mob = device == "Mobile"
        vp_w = 390 if mob else 1280
        vp_h = 844 if mob else 900
        print(f"\n[Gazeta] {fmt} | {device} | pid={pid}")

        ctx = make_ctx(browser, device)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": "", "clk_url": ""}
        t_ref = [0.0]
        page.on("request", make_listener(flags, t_ref, pid))
        ctx.on("page", lambda np, _f=flags, _t=t_ref, _pid=pid:
               np.on("request", make_listener(_f, _t, _pid)))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [load warn] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3); click_consent(page)
        time.sleep(2); click_consent(page)

        for _ in range(4):
            page.evaluate("window.scrollBy(0, 400)")
            time.sleep(0.5)

        # Poll for IMP — may fire before or after setup, poll catches both
        for i in range(50):
            if flags["imp"]: break
            time.sleep(1)

        if flags["imp"]:
            t_now = time.time() - t_ref[0]
            print(f"  [IMP confirmed at t+{t_now:.0f}s — clicking ad]")
            time.sleep(1)
            click_ad_frame(page, vp_w, vp_h, flags, t_ref, pid)
        else:
            print("  [IMP not seen after 50s]")
            time.sleep(5)

        imp = flags["imp"]; clk = flags["clk"]
        pid_imp = pid in flags["imp_url"] if flags["imp_url"] else False
        pid_clk = pid in flags["clk_url"] if flags["clk_url"] else False
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | imp={'OK' if pid_imp else 'NO'} clk={'OK' if pid_clk else 'NO'}")
        results.append(("Gazeta", fmt, device, pid, status, pid_imp, pid_clk, flags["clk_url"]))
        page.close(); ctx.close()

    browser.close()

print("\n" + "="*65)
print("SUMMARY")
print("="*65)
for pub, fmt, dev, pid, status, pid_imp, pid_clk, clk_url in results:
    clk_src = ""
    if pid_clk and clk_url:
        if "retailclient" in clk_url.lower(): clk_src = " [retailclient popup]"
        elif "trackclk" in clk_url: clk_src = " [CM360 trackclk]"
    print(f"  [{status:<8}] {pub} | {fmt} | {dev} | imp={'OK' if pid_imp else '??'} clk={'OK' if pid_clk else '??'}{clk_src}")

try:
    log.close()
except: pass
