"""
HVP Commercial Break v4 — real Playwright mouse click (isTrusted=true).
JS a.click() is synthetic (isTrusted=false) so WP's CB interceptor ignores it.
Must use page.mouse.click() or locator.click() to generate a trusted event.
"""
from playwright.sync_api import sync_playwright
import time, sys

CAMPAIGN_ID = "90000001"
UA_D = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

HVP_ROWS = [
    ("CB XL mobile",   "Mobile",  "900000022", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_1_desktop_clothing&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690209%22%7D%5D&testPos=2"),
    ("CB XL Clothing", "Desktop", "900000037", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_2_desktop_bekkin&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690210%22%7D%5D&testPos=2"),
    ("CB XL Bekkin",   "Desktop", "900000048", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=L4_3_desktop_barcelona&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484053%2Fiaq%2FBaner_Commercial_Break%2F1690211%22%7D%5D&testPos=2"),
    ("CB XL FC Barca", "Desktop", "900000054", "https://kobieta.wp.pl?wfName=281213_3086396_Retailclient_Kobieta_CBreak_01&creName=360x600_mobile&tcidma=%5B%7B%22slot%22%3A%22002%22%2C%22id%22%3A%22206081%2F1484054%2Fiaq%2FBaner_Commercial_Break%2F1690208%22%7D%5D&testPos=2"),
]

BAD_KEYWORDS = ['premium', 'redakcja', 'regulamin', 'kontakt', '/#', '/tag/',
                'testy-kons', '/wp-content', '.jpg', '.png', '.css', '.js',
                'polityka-prywatnosci', 'newsletter', 'rss', 'sitemap']

def click_consent(page):
    phrases = ['Akceptuję', 'Akceptuj wszystkie', 'Akceptuj', 'Accept all', 'AKCEPTUJĘ', 'Przejdź do serwisu']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t = (el.innerText || el.textContent || '').trim().toUpperCase();
                if (p.some(x => t === x.toUpperCase() || t.startsWith(x.toUpperCase()))) {
                    el.click(); return t;
                }
            } return null;
        }""", phrases)
        if ok: return True
    except: pass
    for sel in ["#onetrust-accept-btn-handler", ".fc-primary-button", "[data-cmp-exp='acceptAll']", ".cmp__btn--accept-all"]:
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
            _f["imp"] = True; _f["imp_url"] = u[:160]
            print(f"    [IMP t+{t:.0f}s] {'PID_OK' if pid_ok else 'PID_MISS'} {u[35:110]}")
        elif 'trackclk' in u and not _f["clk"]:
            _f["clk"] = True
            print(f"    [CLK t+{t:.0f}s] {'PID_OK' if pid_ok else ''}")
        elif 'doubleclick.net' in u and 'trackimp' not in u and 'trackclk' not in u:
            print(f"    [DC t+{t:.0f}s] {u[35:100]}")
    return on_req

log = open("hvp_v4_results.txt", "w", encoding="utf-8", buffering=1)
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
        page.on("request", make_listener(flags, t_ref, pid))

        # Load test URL with full load wait (ensures WP session JS runs completely)
        try:
            page.goto(url, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"  [load err] {e}")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except: pass

        t_ref[0] = time.time()
        page.bring_to_front()

        # Accept consent (try twice)
        time.sleep(3); click_consent(page)
        time.sleep(2); click_consent(page)
        time.sleep(3)

        print(f"  [page url] {page.url[:80]}")

        # Find a visible article link using Playwright's locator
        # Real click (isTrusted=true) required for WP's CB interceptor
        clicked = False
        try:
            # Try to find and click a visible article link
            all_links = page.locator("a[href*='kobieta.wp.pl']")
            count = all_links.count()
            print(f"  [found {count} kobieta.wp.pl links]")

            for i in range(min(count, 30)):
                try:
                    link = all_links.nth(i)
                    href = link.get_attribute("href") or ""
                    path = href.replace("https://kobieta.wp.pl", "").replace("http://kobieta.wp.pl", "")
                    if len(path) < 15: continue
                    if any(b in href for b in BAD_KEYWORDS): continue
                    if not link.is_visible(timeout=500): continue

                    print(f"  [clicking] {href[:80]}")
                    with page.expect_navigation(timeout=20000):
                        link.click()
                    print(f"  [navigated] -> {page.url[:80]}")
                    clicked = True
                    break
                except Exception as e2:
                    continue

            if not clicked:
                print("  [no visible link — trying scroll + retry]")
                # Scroll down to load more content
                for _ in range(5):
                    page.evaluate("window.scrollBy(0, 500)")
                    time.sleep(0.5)

                for i in range(min(count, 50)):
                    try:
                        link = all_links.nth(i)
                        href = link.get_attribute("href") or ""
                        path = href.replace("https://kobieta.wp.pl", "")
                        if len(path) < 15: continue
                        if any(b in href for b in BAD_KEYWORDS): continue

                        # Try scrolling element into view then clicking
                        link.scroll_into_view_if_needed(timeout=3000)
                        time.sleep(0.3)
                        if link.is_visible(timeout=500):
                            print(f"  [clicking after scroll] {href[:80]}")
                            with page.expect_navigation(timeout=20000):
                                link.click()
                            print(f"  [navigated] -> {page.url[:80]}")
                            clicked = True
                            break
                    except: continue

        except Exception as e:
            print(f"  [click phase err] {e}")

        if not clicked:
            print("  [WARN] Could not click any article link")

        # Wait on destination page for CB impression
        # CB may fire as overlay/interstitial on the article page
        time.sleep(25)

        imp = flags["imp"]
        clk = flags["clk"]
        pid_c = pid in flags["imp_url"] if (pid and flags["imp_url"]) else None
        status = "PASS" if imp and clk else "IMP ONLY" if imp else "NO TAG"
        print(f"  >> {status} | pid={'OK' if pid_c else 'CHECK'} | clicked={clicked}")
        results.append((fmt, device, pid, status, pid_c, clicked))
        page.close()
        ctx.close()

    browser.close()

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
for fmt, dev, pid_v, status, pid_c, clicked in results:
    print(f"  [{status:<8}] HVP | {fmt} | {dev} | pid={'OK' if pid_c else '??'} | clicked={clicked}")

log.close()
