"""
HVP Commercial Break - click real article after loading test URL.
HybridAI - longer load timeout.
"""
from playwright.sync_api import sync_playwright
import re, time, sys

CAMPAIGN_ID = "90000001"

UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

HVP_ROWS = [
    ("HVP", "CB XL mobile",   "Mobile",  "900000022", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_1_desktop_clothing&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690209%22%7D%5D&testPos=2"),
    ("HVP", "CB XL Clothing", "Desktop", "900000037", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_2_desktop_bekkin&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690210%22%7D%5D&testPos=2"),
    ("HVP", "CB XL Bekkin",   "Desktop", "900000048", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_3_desktop_barcelona&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690211%22%7D%5D&testPos=2"),
    ("HVP", "CB XL FC Barca", "Desktop", "900000054", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=360x600_mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484054%2Fiaq%2FBaner_Commercial_Break%2F1690208%22%7D%5D&testPos=2"),
]

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
    for sel in ["#onetrust-accept-btn-handler",".fc-primary-button","[data-cmp-exp='acceptAll']"]:
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
        if 'trackimp' in u and not _f["imp"] and (pid_ok or not _pid):
            _f["imp"] = True; _f["imp_url"] = u
            print(f"    [IMP t+{t:.0f}s] {'PID_OK' if pid_ok else 'no_pid'} {u[35:110]}")
        elif 'trackclk' in u and not _f["clk"] and (pid_ok or not _pid):
            _f["clk"] = True
            print(f"    [CLK t+{t:.0f}s]")
    return on_req

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # ── HVP Commercial Break ────────────────────────────────────────────────────
    print("="*60)
    print("HVP Commercial Break — test URL then navigate to real article")
    print("="*60)

    for publisher, fmt, device, pid, url in HVP_ROWS:
        mob = device == "Mobile"
        print(f"\n[{publisher}] {fmt} | {device} | pid={pid}")

        ctx = make_ctx(browser, device)
        pg_warm = ctx.new_page()

        # Step 1: consent warmup on homepage
        pg_warm.goto("https://kobieta.wp.pl/", wait_until="domcontentloaded", timeout=20000)
        pg_warm.bring_to_front(); time.sleep(4)
        click_consent(pg_warm); time.sleep(2)

        # Find an article link from the homepage
        article_url = pg_warm.evaluate("""() => {
            const candidates = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const h = a.href || '';
                if (!h.includes('kobieta.wp.pl')) continue;
                const path = h.replace(/https?:\\/\\/kobieta\\.wp\\.pl/, '');
                // real article paths: /artykul/, or /{category},{id}, or long paths with numbers
                if (path.length > 20 && !path.startsWith('/?') && !path.startsWith('/redakcja')
                    && !path.startsWith('/testy') && !path.startsWith('/tag')
                    && (path.match(/\\/\\w[^?#]{15,}/) || path.match(/,\\d{6,}/))) {
                    candidates.push(h);
                }
            }
            return candidates[0] || null;
        }""")
        pg_warm.close()

        print(f"  [article found] {article_url[:80] if article_url else 'NONE'}")

        # Step 2: load test URL (sets test cookie/session)
        pg_test = ctx.new_page()
        flags = {"imp": False, "clk": False, "imp_url": ""}
        t_ref = [0.0]
        pg_test.on("request", make_listener(flags, t_ref, pid))

        try:
            pg_test.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            print(f"  [test url load err] {e}")

        t_ref[0] = time.time()
        pg_test.bring_to_front()
        time.sleep(3); click_consent(pg_test); time.sleep(2)

        # Step 3: navigate to the article — CB fires between pages
        if article_url:
            print(f"  [navigating to article...]")
            try:
                pg_test.goto(article_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                print(f"  [article nav err] {e}")
        else:
            # Fallback: click a visible link
            print(f"  [clicking first available link...]")
            try:
                pg_test.locator("a[href*='kobieta.wp.pl']").first.click()
            except: pass

        time.sleep(15)

        imp = flags["imp"]; clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
        results.append((publisher, fmt, device, pid, status, pid_c))
        pg_test.close(); ctx.close()

    # ── HybridAI ───────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("HybridAI deaz.io — longer timeout")
    print("="*60)

    ctx = make_ctx(browser, "Mobile")
    page = ctx.new_page()
    flags = {"imp": False, "clk": False, "imp_url": ""}
    t_ref = [0.0]
    pid = "900000069"
    page.on("request", make_listener(flags, t_ref, pid))

    print(f"\n[HybridAI] Richmedia | Mobile | pid={pid}")
    try:
        page.goto("https://app.deaz.io/preview/?ad=6a69d4118e4e3f8dc29beb50",
                  wait_until="domcontentloaded", timeout=60000)
        print("  [loaded ok]")
    except Exception as e:
        print(f"  [load err] {e}")

    t_ref[0] = time.time()
    page.bring_to_front()
    time.sleep(5); click_consent(page); time.sleep(3)
    try: page.mouse.click(195, 400)
    except: pass
    time.sleep(15)

    imp = flags["imp"]; clk = flags["clk"]
    pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
    status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
    print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'}")
    results.append(("HybridAI", "Richmedia", "Mobile", pid, status, pid_c))
    page.close(); ctx.close()

    browser.close()

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for pub, fmt, dev, pid_val, status, pid_c in results:
    print(f"  [{status:<8}] {pub} | {fmt} | {dev} | pid={'OK' if pid_c else '??'}")
