"""
BTS 2026 — targeted re-run for problematic rows + unrun rows.
Longer waits for Gazeta/OLX, full scroll for HVP/Agora, investigate MCN.
"""
from playwright.sync_api import sync_playwright
import re, time, sys

CAMPAIGN_ID = "90000001"

RERUN = [
    # MCN — investigate what fires on v-test.online
    ("MCN",      "L-frame FC Barcelona", "Desktop", "900000022", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjEvMzgw?position=horizontal&template=ecommerce"),
    ("MCN",      "L-frame Bekkin",       "Desktop", "900000039", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjIvMzgx?position=horizontal&template=ecommerce"),
    ("MCN",      "L-frame Clothing",     "Desktop", "900000042", "https://demo.v-test.online/aHR0cHM6Ly9zeXN0ZW0ubWNuZXR3b3JrLnBsL2VuL2RlbW8vMTgtMzg1LXBlcGNvLWVsa2EtdjMvMzgy?position=horizontal&template=ecommerce"),
    # HVP Commercial Break — longer scroll
    ("HVP",      "CB XL mobile",         "Mobile",  "900000052", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_1_desktop_clothing&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690209%22%7D%5D&testPos=2"),
    ("HVP",      "CB XL Clothing",       "Desktop", "900000067", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_2_desktop_bekkin&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690210%22%7D%5D&testPos=2"),
    ("HVP",      "CB XL Bekkin",         "Desktop", "900000078", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_3_desktop_barcelona&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690211%22%7D%5D&testPos=2"),
    ("HVP",      "CB XL FC Barca",       "Desktop", "900000084", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=360x600_mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484054%2Fiaq%2FBaner_Commercial_Break%2F1690208%22%7D%5D&testPos=2"),
    # Gazeta/OLX slow loaders — 40s wait
    ("Gazeta",   "12-Aug Mobile",        "Mobile",  "900000091", "https://www.chillizet.pl/?google_preview=PLACEHOLDER&iu=90000010&gdfp_req=1&lineItemId=9000001160&creativeId=900000129157"),
    ("Gazeta",   "18-Aug Desktop",       "Desktop", "900000055", "https://www.wysokieobcasy.pl/wysokie-obcasy/0,0.html?google_preview=PLACEHOLDER&iu=90000010&gdfp_req=1&lineItemId=9000001344&creativeId=900000142653"),
    ("HPH",      "OLX Listing",          "Desktop", "900000155", "https://www.olx.pl/moda?google_preview=PLACEHOLDER&iu=90000016&gdfp_req=1&lineItemId=9000001755&creativeId=900000185013"),
    ("HPH",      "OLX Ad page",          "Desktop", "900000155", "https://www.olx.pl/d/oferta/skorzane-sneakersy-kapri-karl-lagerfeld-CID87-ID1aOgig.html?google_preview=PLACEHOLDER&iu=90000016&gdfp_req=1&lineItemId=9000001908&creativeId=900000185202"),
    # Agora Midscroll — scroll through long article
    ("HPH",      "Agora Midscroll",      "Mobile",  "900000097", "https://www.plotek.pl/plotek/7,111485,90000020,sean-paul-spoznil-sie-na-wlasny-koncert-w-lodzi-teraz-sie-tlumaczy.html?google_preview=PLACEHOLDER&iu=90000010&gdfp_req=1&lineItemId=9000002152&creativeId=90000022642"),
    # Polsat lpmobiem retry
    ("Polsat",   "Interstitial lpmobiem","Mobile",  "900000239", "https://lpmobiem.civ.pl/retailclient02/"),
    # Not yet run
    ("HybridAI", "Richmedia",            "Mobile",  "900000249", "https://app.deaz.io/preview/?ad=6a69d4118e4e3f8dc29beb50"),
    ("Teads",    "Video Skin L",         "Desktop", "",          "https://demo.teads.com/?content=publishers%2Fteads-tech-english.html&vast=https%3A%2F%2Fs8t.teads.tv%2Fvast%2F9000002590000026"),
    ("Teads",    "Video Skin SQ",        "Desktop", "",          "https://demo.teads.com/?content=publishers%2Fteads-tech-english.html&vast=https%3A%2F%2Fs8t.teads.tv%2Fvast%2F9000002590000027"),
]

UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

def make_ctx(browser, device):
    mob = device == "Mobile"
    return browser.new_context(
        viewport={"width": 390, "height": 844} if mob else {"width": 1280, "height": 900},
        locale="pl-PL", user_agent=UA_M if mob else UA_D, ignore_https_errors=True)

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Accept all','Zgadzam się','AKCEPTUJĘ','Przejdź do serwisu']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t=(el.innerText||el.textContent||'').trim().toUpperCase();
                if(p.some(x=>t===x.toUpperCase()||t.startsWith(x.toUpperCase()))){el.click();return t;}
            } return null;
        }""", phrases)
        if ok: return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']",".cmp__btn--accept-all","[class*='accept-all']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click(); return True
        except: pass
    return False

log = open("bts2026_rerun.txt", "w", encoding="utf-8", buffering=1)
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

    print("[warmup consent]")
    warmups = [
        ("wp mob",        "https://kobieta.wp.pl/",       "Mobile"),
        ("wp dsk",        "https://kobieta.wp.pl/",       "Desktop"),
        ("chillizet mob", "https://www.chillizet.pl/",    "Mobile"),
        ("wysokieobcasy", "https://www.wysokieobcasy.pl/","Desktop"),
        ("plotek mob",    "https://www.plotek.pl/",       "Mobile"),
        ("olx dsk",       "https://www.olx.pl/",         "Desktop"),
    ]
    shared = {}
    for key, site, device in warmups:
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

    for i, (publisher, fmt, device, placement_id, url) in enumerate(RERUN):
        mob = device == "Mobile"
        domain = re.search(r'https?://([^/?]+)', url)
        domain = domain.group(1) if domain else ''

        is_wp      = 'kobieta.wp.pl' in domain
        is_gam     = 'google_preview' in url
        is_mcn     = 'v-test.online' in domain
        is_teads   = 'teads.com' in domain
        is_polsat  = 'civ.pl' in domain or 'spicymobile.pl' in domain
        is_deaz    = 'deaz.io' in domain

        if 'kobieta.wp.pl' in domain:
            ctx = shared["wp mob" if mob else "wp dsk"]; owned = False
        elif 'chillizet.pl' in domain:
            ctx = shared["chillizet mob"]; owned = False
        elif 'wysokieobcasy.pl' in domain:
            ctx = shared["wysokieobcasy"]; owned = False
        elif 'plotek.pl' in domain:
            ctx = shared["plotek mob"]; owned = False
        elif 'olx.pl' in domain:
            ctx = shared["olx dsk"]; owned = False
        else:
            ctx = make_ctx(browser, device); owned = True

        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": "", "all_dc": []}
        t_ref = [0.0]

        def on_req(req, _f=flags, _t=t_ref, _pid=placement_id, _cid=CAMPAIGN_ID):
            u = req.url
            if 'doubleclick.net' not in u and 'dc_trk' not in u:
                return
            t = time.time() - _t[0] if _t[0] else 0
            m = re.search(r'dc_trk_aid=(\d+)', u)
            if m and m.group(1) not in _f["all_dc"]:
                _f["all_dc"].append(m.group(1))
            pid_ok = _pid and _pid in u
            if 'trackimp' in u and not _f["imp"] and (pid_ok or not _pid):
                _f["imp"] = True; _f["imp_url"] = u[:160]
                print(f"    [IMP t+{t:.0f}s] {'PID_OK' if pid_ok else 'no_pid'} {u[35:110]}")
            elif 'trackclk' in u and not _f["clk"] and (pid_ok or not _pid):
                _f["clk"] = True
                print(f"    [CLK t+{t:.0f}s] {u[35:80]}")

        page.on("request", on_req)
        print(f"\n[{i+1:2}/{len(RERUN)}] {publisher} | {fmt} | {device} | pid={placement_id or 'N/A'}")
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

        if is_mcn:
            # Scroll through the MCN demo frame + click
            time.sleep(5)
            try: page.mouse.click(640, 450)
            except: pass
            time.sleep(3)
            for _ in range(10):
                try: page.evaluate("window.scrollBy(0, 200)")
                except: pass
                time.sleep(0.5)
            time.sleep(5)
        elif is_wp:
            # Commercial Break requires scrolling past article content
            for _ in range(30):
                try: page.evaluate("window.scrollBy(0, 300)")
                except: pass
                time.sleep(0.5)
            time.sleep(8)
            for _ in range(15):
                try: page.evaluate("window.scrollBy(0, 300)")
                except: pass
                time.sleep(0.5)
            time.sleep(5)
        elif is_gam:
            # Gazeta/OLX: 40s wait
            time.sleep(40)
        elif is_teads:
            time.sleep(5)
            try: page.mouse.click(640, 360)
            except: pass
            time.sleep(10)
            # Also try pressing spacebar for video play
            try: page.keyboard.press("Space")
            except: pass
            time.sleep(8)
        elif is_polsat:
            time.sleep(12)
        elif is_deaz:
            time.sleep(12)
            try: page.mouse.click(195, 400)
            except: pass
            time.sleep(5)
        else:
            time.sleep(10)

        if not flags["imp"]:
            time.sleep(10)

        imp = flags["imp"]; clk = flags["clk"]
        pid_conf = placement_id in flags["imp_url"] if (placement_id and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "CLK ONLY" if clk else "NO TAG"

        pid_note = f" pid={'OK' if pid_conf else 'CHECK' if pid_conf is None else 'MISS'}" if placement_id else ""
        print(f"  >> {status}{pid_note}")
        if not imp and flags["all_dc"]:
            print(f"  other aids: {flags['all_dc'][:5]}")

        results.append((publisher, fmt, device, placement_id, status, imp, clk, pid_conf))
        page.close()
        if owned: ctx.close()

    browser.close()

print("\n" + "="*70)
print("RERUN SUMMARY")
print("="*70)
for pub, fmt, dev, pid, status, imp, clk, pid_conf in results:
    pid_note = f" | pid={'OK' if pid_conf else '??' if pid_conf is None else 'MISS'}" if pid else ""
    print(f"  [{status:<8}] {pub:<10} {fmt:<25} {dev}{pid_note}")

log.close()
