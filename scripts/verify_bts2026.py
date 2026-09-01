"""
Retailclient BTS 2026 — Campaign 90000001
Verifies: CM360 impression fires with correct B90000001.{placement_id} in URL
"""
from playwright.sync_api import sync_playwright
import re, time, sys

CAMPAIGN_ID = "90000001"

ROWS = [
    ("MCN",      "L-frame FC Barcelona",          "Desktop", "900000022", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjEvMzgw?position=horizontal&template=ecommerce"),
    ("MCN",      "L-frame Bekkin",                "Desktop", "900000039", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjIvMzgx?position=horizontal&template=ecommerce"),
    ("MCN",      "L-frame Clothing",              "Desktop", "900000042", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjMvMzgy?position=horizontal&template=ecommerce"),
    ("HVP",      "Commercial Break XL",           "Mobile",  "900000052", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_1_desktop_clothing&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690209%22%7D%5D&testPos=2"),
    ("HVP",      "Commercial Break XL Clothing",  "Desktop", "900000067", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_2_desktop_bekkin&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690210%22%7D%5D&testPos=2"),
    ("HVP",      "Commercial Break XL Bekkin",    "Desktop", "900000078", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_3_desktop_barcelona&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690211%22%7D%5D&testPos=2"),
    ("HVP",      "Commercial Break XL FC Barca",  "Desktop", "900000084", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=360x600_mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484054%2Fiaq%2FBaner_Commercial_Break%2F1690208%22%7D%5D&testPos=2"),
    ("WP",       "Dniowka screening HTML",        "Desktop", "900000099", "https://kobieta.wp.pl/?wfName=281211_3079984_Retailclient_Kobieta_retail_1dniowka_01&creName=scr_html&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22206091%2F1484076%2Fiaq%2FRetaildni%5Cu00f3wka_2_Desktop_ROS_Screening_v2%2F1690268%22%7D%5D&testPos=3"),
    ("WP",       "Dniowka screening JPG",         "Desktop", "900000099", "https://kobieta.wp.pl/?wfName=281211_3079984_Retailclient_Kobieta_retail_1dniowka_01&creName=scr_statyk&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22206091%2F1484076%2Fiaq%2FRetaildni%5Cu00f3wka_2_Desktop_ROS_Screening_v2%2F1690269%22%7D%5D&testPos=3"),
    ("WP",       "Dniowka banner HTML",           "Desktop", "900000099", "https://kobieta.wp.pl/?wfName=281211_3079984_Retailclient_Kobieta_retail_1dniowka_01&creName=L4_970_html&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22206091%2F1484076%2Fiaq%2FRetaildni%5Cu00f3wka_2_Desktop%2F1690270%22%7D%5D&testPos=3"),
    ("WP",       "Dniowka banner JPG",            "Desktop", "900000099", "https://kobieta.wp.pl/?wfName=281211_3079984_Retailclient_Kobieta_retail_1dniowka_01&creName=L4_970_statyk&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22206091%2F1484076%2Fiaq%2FRetaildni%5Cu00f3wka_2_Desktop%2F1690276%22%7D%5D&testPos=3"),
    ("WP",       "Dniowka mobile HTML",           "Mobile",  "900000099", "https://kobieta.wp.pl?wfName=281211_3079984_Retailclient_Kobieta_retail_1dniowka_01&creName=mobile_400&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22206091%2F1484076%2Fiaq%2FRetaildni%5Cu00f3wka_2_Mobile%2F1690277%22%7D%5D&testPos=1"),
    ("WP",       "Dniowka mobile JPG",            "Mobile",  "900000099", "https://kobieta.wp.pl?wfName=281211_3079984_Retailclient_Kobieta_retail_1dniowka_01&creName=mobile_200&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22206091%2F1484076%2Fiaq%2FRetaildni%5Cu00f3wka_2_Mobile%2F1690284%22%7D%5D&testPos=1"),
    ("Inis",     "Inis",                          "Desktop", "900000102", "https://system.inis360.com/banners-test/76c536a9-f784-4740-8a44-d8ab1ae0d69a/FULLSIX%20MEDIA/203785"),
    ("Gazeta",   "12-Aug Desktop",                "Desktop", "900000111", "https://kobieta.gazeta.pl/kobieta/0,0.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001360&creativeId=900000148182"),
    ("Gazeta",   "12-Aug Mobile",                 "Mobile",  "900000111", "https://www.chillizet.pl/?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001360&creativeId=900000149157"),
    ("Gazeta",   "18-Aug Desktop",                "Desktop", "900000055", "https://www.wysokieobcasy.pl/wysokie-obcasy/0,0.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001544&creativeId=900000162653"),
    ("Gazeta",   "18-Aug Mobile",                 "Mobile",  "900000055", "https://www.plotek.pl/plotek/0,0.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001544&creativeId=900000179047"),
    ("HPH",      "Agora Midscroll",               "Mobile",  "900000117", "https://www.plotek.pl/plotek/7,111485,90000018,sean-paul-spoznil-sie-na-wlasny-koncert-w-lodzi-teraz-sie-tlumaczy.html?google_preview=PLACEHOLDER&iu=90000012&gdfp_req=1&lineItemId=9000001952&creativeId=90000020642"),
    ("HPH",      "OLX Homepage",                  "Desktop", "900000215", "https://www.olx.pl/?creativeId=900000224797&gdfp_req=1&google_preview=PLACEHOLDER&iu=90000023&lineItemId=9000002411"),
    ("HPH",      "OLX Listing",                   "Desktop", "900000215", "https://www.olx.pl/moda?google_preview=PLACEHOLDER&iu=90000023&gdfp_req=1&lineItemId=9000002555&creativeId=900000225013"),
    ("HPH",      "OLX Ad page",                   "Desktop", "900000215", "https://www.olx.pl/d/oferta/skorzane-sneakersy-kapri-karl-lagerfeld-CID87-ID1aOgig.html?google_preview=PLACEHOLDER&iu=90000023&gdfp_req=1&lineItemId=9000002408&creativeId=900000225202"),
    ("Polsat",   "Interstitial lpmobiem",         "Mobile",  "900000269", "https://lpmobiem.civ.pl/retailclient02/"),
    ("Polsat",   "Interstitial pmk",              "Mobile",  "900000269", "https://pmk.spicymobile.pl/11421RetailclientBTS/1ZK5HE"),
    ("HybridAI", "Richmedia",                     "Mobile",  "900000279", "https://app.deaz.io/preview/?ad=6a69d4118e4e3f8dc29beb50"),
    ("Teads",    "Video Skin L",                  "Desktop", "",          "https://demo.teads.com/?content=publishers%2Fteads-tech-english.html&vast=https%3A%2F%2Fs8t.teads.tv%2Fvast%2F9000002890000029"),
    ("Teads",    "Video Skin SQ",                 "Desktop", "",          "https://demo.teads.com/?content=publishers%2Fteads-tech-english.html&vast=https%3A%2F%2Fs8t.teads.tv%2Fvast%2F9000002890000030"),
]

UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

def make_ctx(browser, device):
    mob = device == "Mobile"
    return browser.new_context(
        viewport={"width": 390, "height": 844} if mob else {"width": 1280, "height": 900},
        locale="pl-PL", user_agent=UA_M if mob else UA_D, ignore_https_errors=True)

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all','Zgadzam się',
               'AKCEPTUJĘ','Przejdź do serwisu','Akceptuj i przejdź']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t = (el.innerText||el.textContent||'').trim().toUpperCase();
                if (p.some(x => t===x.toUpperCase()||t.startsWith(x.toUpperCase()))) {el.click(); return t;}
            } return null;
        }""", phrases)
        if ok: return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']",
                ".cmp__btn--accept-all","[class*='accept-all']","[class*='consent-accept']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); return True
        except: pass
    return False

log = open("bts2026_results.txt", "w", encoding="utf-8", buffering=1)
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

    # Warmup consent for publisher sites
    print("[=== Consent Warmup ===]")
    warmup_sites = [
        ("kobieta.wp.pl",      "https://kobieta.wp.pl/",      "Desktop"),
        ("kobieta.wp.pl mob",  "https://kobieta.wp.pl/",      "Mobile"),
        ("gazeta.pl",          "https://kobieta.gazeta.pl/",  "Desktop"),
        ("chillizet mob",      "https://www.chillizet.pl/",   "Mobile"),
        ("wysokieobcasy",      "https://www.wysokieobcasy.pl/","Desktop"),
        ("plotek mob",         "https://www.plotek.pl/",      "Mobile"),
        ("olx",                "https://www.olx.pl/",         "Desktop"),
    ]
    shared = {}
    for key, site, device in warmup_sites:
        ctx = make_ctx(browser, device)
        pg = ctx.new_page()
        try:
            pg.goto(site, wait_until="domcontentloaded", timeout=20000)
            pg.bring_to_front(); time.sleep(5)
            ok = click_consent(pg); time.sleep(2)
            print(f"  {key} consent={ok}")
        except Exception as e:
            print(f"  [warn] {key}: {e}")
        finally:
            pg.close()
        shared[key] = ctx

    print("\n" + "="*70)
    print(f"VERIFICATION — Campaign {CAMPAIGN_ID}")
    print("="*70)

    for i, (publisher, fmt, device, placement_id, url) in enumerate(ROWS):
        mob = device == "Mobile"
        domain = re.search(r'https?://([^/?]+)', url)
        domain = domain.group(1) if domain else ''

        # Pick context
        if 'kobieta.wp.pl' in domain:
            ctx = shared["kobieta.wp.pl mob" if mob else "kobieta.wp.pl"]; owned = False
        elif 'kobieta.gazeta.pl' in domain:
            ctx = shared["gazeta.pl"]; owned = False
        elif 'chillizet.pl' in domain:
            ctx = shared["chillizet mob"]; owned = False
        elif 'wysokieobcasy.pl' in domain:
            ctx = shared["wysokieobcasy"]; owned = False
        elif 'plotek.pl' in domain:
            ctx = shared["plotek mob"]; owned = False
        elif 'olx.pl' in domain:
            ctx = shared["olx"]; owned = False
        else:
            ctx = make_ctx(browser, device); owned = True

        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": "", "any_dc": []}
        t_ref = [0.0]

        def on_req(req, _f=flags, _t=t_ref, _pid=placement_id, _cid=CAMPAIGN_ID):
            u = req.url
            if 'doubleclick.net' not in u and 'dc_trk' not in u:
                return
            t = time.time() - _t[0] if _t[0] else 0
            m_aid = re.search(r'dc_trk_aid=(\d+)', u)
            if m_aid and m_aid.group(1) not in _f["any_dc"]:
                _f["any_dc"].append(m_aid.group(1))
            pid_match = _pid and _pid in u
            camp_match = _cid in u
            if 'trackimp' in u and not _f["imp"] and (pid_match or not _pid):
                _f["imp"] = True
                _f["imp_url"] = u[:150]
                pid_ok = "[PID OK]" if pid_match else "[PID MISS]" if _pid else "[no pid]"
                print(f"    [IMP t+{t:.0f}s] {pid_ok} {u[35:120]}")
            elif 'trackclk' in u and not _f["clk"] and (pid_match or not _pid):
                _f["clk"] = True
                print(f"    [CLK t+{t:.0f}s] {u[35:80]}")

        page.on("request", on_req)

        print(f"\n[{i+1:2}/{len(ROWS)}] {publisher} | {fmt} | {device} | pid={placement_id or 'N/A'}")
        print(f"  {url[:90]}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [load err] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3)
        click_consent(page); time.sleep(2)
        click_consent(page); time.sleep(2)

        is_wp = 'kobieta.wp.pl' in domain
        is_gam = 'google_preview' in url
        is_mcn = 'v-test.online' in domain
        is_teads = 'teads.com' in domain
        is_polsat = 'civ.pl' in domain or 'spicymobile.pl' in domain
        is_deaz = 'deaz.io' in domain
        is_inis = 'inis360.com' in domain

        if is_wp:
            # Scroll for WP ads
            for _ in range(15):
                try: page.evaluate("window.scrollBy(0, 300)")
                except: pass
                time.sleep(0.5)
            time.sleep(5)
        elif is_gam:
            time.sleep(12)
        elif is_mcn:
            # MCN demo - wait and try clicking
            time.sleep(8)
            try: page.mouse.click(640, 450)
            except: pass
            time.sleep(5)
        elif is_teads:
            # Teads video player - click play
            time.sleep(5)
            try: page.mouse.click(640, 360)
            except: pass
            time.sleep(8)
        elif is_polsat:
            time.sleep(10)
        elif is_deaz:
            time.sleep(10)
        elif is_inis:
            time.sleep(8)
        else:
            time.sleep(8)

        # Extra wait if nothing yet
        if not flags["imp"]:
            time.sleep(8)

        imp = flags["imp"]; clk = flags["clk"]
        if imp and clk:     status = "PASS"
        elif imp:           status = "IMP ONLY"
        elif clk:           status = "CLK ONLY"
        else:               status = "NO TAG"

        pid_confirmed = placement_id in flags["imp_url"] if (placement_id and flags["imp_url"]) else None

        print(f"  >> {status}" + (f" | placement={'CONFIRMED' if pid_confirmed else 'CHECK' if pid_confirmed is None else 'MISMATCH'}" if placement_id else ""))
        if flags["any_dc"] and not flags["imp"]:
            print(f"  Other aids seen: {flags['any_dc'][:5]}")

        results.append((publisher, fmt, device, placement_id, status, imp, clk, pid_confirmed))
        page.close()
        if owned: ctx.close()

    browser.close()

# Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
passed = imp_ok = 0
for pub, fmt, dev, pid, status, imp, clk, pid_conf in results:
    mark = f"[{status:<8}]"
    pid_note = f" | pid={'OK' if pid_conf else '??' if pid_conf is None else 'MISS'}" if pid else ""
    print(f"  {mark} {pub:<10} {fmt:<32} {dev:<8}{pid_note}")
    if status == "PASS": passed += 1
    if imp: imp_ok += 1

total = len(results)
print(f"\n{passed}/{total} PASS  |  {imp_ok}/{total} IMP confirmed  |  {total-imp_ok}/{total} need attention")
log.close()
