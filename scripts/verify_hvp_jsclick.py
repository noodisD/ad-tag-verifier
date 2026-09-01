"""HVP CB — JS click on article link to trigger WP's interstitial handler."""
from playwright.sync_api import sync_playwright
import re, time

CAMPAIGN_ID = "90000001"
UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

HVP_ROWS = [
    ("CB XL mobile",   "Mobile",  "900000022", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_1_desktop_clothing&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690209%22%7D%5D&testPos=2"),
    ("CB XL Clothing", "Desktop", "900000037", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_2_desktop_bekkin&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690210%22%7D%5D&testPos=2"),
    ("CB XL Bekkin",   "Desktop", "900000048", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_3_desktop_barcelona&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690211%22%7D%5D&testPos=2"),
    ("CB XL FC Barca", "Desktop", "900000054", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=360x600_mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484054%2Fiaq%2FBaner_Commercial_Break%2F1690208%22%7D%5D&testPos=2"),
]

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','AKCEPTUJĘ','Przejdź do serwisu','Accept all']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t=(el.innerText||el.textContent||'').trim().toUpperCase();
                if(p.some(x=>t===x.toUpperCase()||t.startsWith(x.toUpperCase()))){el.click();return t;}
            } return null;
        }""", phrases)
        if ok: return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=600):
                page.locator(sel).first.click(); return True
        except: pass
    return False

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    for fmt, device, pid, url in HVP_ROWS:
        mob = device == "Mobile"
        ua = UA_M if mob else UA_D
        vp = {"width": 390, "height": 844} if mob else {"width": 1280, "height": 900}

        print(f"\n{'='*60}")
        print(f"[HVP] {fmt} | {device} | pid={pid}")

        ctx = browser.new_context(viewport=vp, locale="pl-PL", user_agent=ua, ignore_https_errors=True)
        page = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]

        def on_req(req, _f=flags, _t=t_ref, _pid=pid):
            u = req.url
            if 'doubleclick.net' not in u and 'dc_trk' not in u: return
            t = time.time() - _t[0] if _t[0] else 0
            if 'trackimp' in u and not _f["imp"] and (_pid in u):
                _f["imp"] = True; _f["imp_url"] = u
                print(f"    [IMP t+{t:.0f}s] PID_OK {u[35:110]}")
            elif 'trackclk' in u and not _f["clk"] and (_pid in u):
                _f["clk"] = True
                print(f"    [CLK t+{t:.0f}s]")

        page.on("request", on_req)

        # Load test URL
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [load err] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()
        time.sleep(3); click_consent(page); time.sleep(3); click_consent(page); time.sleep(2)

        # JS click — bypasses visibility, still fires event handlers
        clicked = page.evaluate("""() => {
            const bad = ['premium','redakcja','regulamin','kontakt','/#','tag/',
                         'testy-kons','/wp-content','.jpg','.png','.css','.js'];
            for (const a of document.querySelectorAll('a[href]')) {
                const h = a.href;
                if (!h.includes('kobieta.wp.pl')) continue;
                const path = h.replace(/https?:\\/\\/kobieta\\.wp\\.pl/, '');
                if (path.length < 15) continue;
                if (bad.some(b => h.includes(b))) continue;
                a.click();
                return h;
            }
            return null;
        }""")
        print(f"  [JS clicked] {str(clicked)[:80] if clicked else 'no link found'}")

        time.sleep(20)

        # If still no imp, maybe CB needs another click/navigation
        if not flags["imp"]:
            print("  [no imp yet — trying second click on any link]")
            clicked2 = page.evaluate("""() => {
                for (const a of document.querySelectorAll('a[href*="kobieta.wp.pl"]')) {
                    if (a.href.length > 40) { a.click(); return a.href; }
                }
                return null;
            }""")
            print(f"  [2nd click] {str(clicked2)[:80] if clicked2 else 'none'}")
            time.sleep(10)

        imp = flags["imp"]; clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if flags["imp_url"] else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
        results.append((fmt, device, pid, status, pid_c))
        page.close(); ctx.close()

    browser.close()

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for fmt, dev, pid_v, status, pid_c in results:
    print(f"  [{status:<8}] HVP | {fmt} | {dev} | pid={'OK' if pid_c else '??'}")
