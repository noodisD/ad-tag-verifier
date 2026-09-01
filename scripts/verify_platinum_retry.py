"""
PLATINUM 600x400 Pudelek — retry with full page load + extended wait
Expected bn=90000001
"""
from playwright.sync_api import sync_playwright
import re, time, sys

URL = "https://pudelek.pl?wfName=276551_3073523_BankClient_pakiet_giga_01&creName=600x400&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22200340%2F1459198%2Fiaq%2FBaner%2F1581576%22%7D%5D&testPos=1"
EXPECTED_BN = 90000001

CONSENT_SELECTORS = [
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj wszystko')",
    "button:has-text('Akceptuj')", "button:has-text('Akceptuję')",
    "button:has-text('Zgadzam się')", "button:has-text('Accept all')",
    "#onetrust-accept-btn-handler", ".js-accept-all", "[class*='accept-all']",
    "button[data-cy='accept-all']", "[class*='agree']", "[class*='accept']",
]

def extract_bn(url):
    m = re.search(r'bn=(\d+)', url)
    return int(m.group(1)) if m else None

def click_consent(page, ms=2000):
    for sel in CONSENT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=ms):
                btn.click()
                print(f"  [consent] {sel}")
                return True
        except Exception:
            pass
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for sel in CONSENT_SELECTORS:
            try:
                btn = frame.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click()
                    print(f"  [consent-iframe] {sel}")
                    return True
            except Exception:
                pass
    return False

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="pl-PL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        # Pre-accept consent on pudelek.pl
        print("[consent-setup] pudelek.pl")
        setup = ctx.new_page()
        try:
            setup.goto("https://www.pudelek.pl/", wait_until="domcontentloaded", timeout=25000)
            setup.bring_to_front()
            time.sleep(6)
            if click_consent(setup, ms=3000):
                time.sleep(2)
                print("[consent-setup] done")
            else:
                print("[consent-setup] no popup")
        except Exception as e:
            print(f"[consent-setup] error: {e}")
        finally:
            setup.close()

        impression_bns = []
        click_bns = []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            if 'adform.net' not in u:
                return
            bn = extract_bn(u)
            t = time.time() - t_ref[0] if t_ref[0] else 0
            # Log ALL adform requests for diagnosis
            print(f"  [ADFORM] {u[:120]}  bn={bn}  t+{t:.1f}s")
            if not bn:
                return
            if 'adfserve' in u or '1x1inv' in u:
                if bn not in impression_bns:
                    impression_bns.append(bn)
                    print(f"  [IMP] bn={bn}  t+{t:.1f}s")
            elif '/C/' in u:
                if bn not in click_bns:
                    click_bns.append(bn)
                    print(f"  [CLK] bn={bn}  t+{t:.1f}s")

        page = ctx.new_page()
        page.on("request", on_req)

        print(f"\n[PLATINUM 600x400 Pudelek]")
        # Try with full load event
        try:
            page.goto(URL, wait_until="load", timeout=45000)
        except Exception as e:
            print(f"  [load warning] {e}")

        t_ref[0] = time.time()
        page.bring_to_front()

        # Inline consent fallback
        if click_consent(page, ms=3000):
            try: page.wait_for_load_state("load", timeout=10000)
            except: pass
            t_ref[0] = time.time()
            impression_bns.clear()
            click_bns.clear()

        # Extended scroll — up to 3 minutes
        print("  [scrolling...]")
        for i in range(150):
            if impression_bns:
                time.sleep(2)
                break
            try:
                page.evaluate("window.scrollBy(0, 300)")
            except Exception:
                pass
            time.sleep(1.2)
            if i % 10 == 0 and i > 0:
                print(f"  [scroll] {i} steps, still waiting...")

        # DOM scan
        for frame in page.frames:
            try:
                links = frame.evaluate("""(() => {
                    const h = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        if (a.href.includes('adform')) h.push(a.href);
                    });
                    return h;
                })()""")
                for link in links:
                    bn = extract_bn(link)
                    if bn and bn not in click_bns:
                        click_bns.append(bn)
                        print(f"  [DOM-CLK] bn={bn}")
            except Exception:
                pass

        page.close()
        browser.close()

        imp_unique = list(set(impression_bns))
        clk_unique = list(set(click_bns))
        imp_ok = bool(EXPECTED_BN in imp_unique)
        clk_ok = bool(EXPECTED_BN in clk_unique)

        status = ("[PASS]"                   if (imp_ok and clk_ok) else
                  "[IMP OK / CLICK MISSING]" if (imp_ok and not clk_ok) else
                  "[FAIL - wrong bn]"        if (imp_unique or clk_unique) else
                  "[NO AD FIRED]")

        print(f"\n  {status}")
        print(f"  Expected  : {EXPECTED_BN}")
        print(f"  Impression: {imp_unique or 'none'}")
        print(f"  Click     : {clk_unique or 'none'}")

if __name__ == "__main__":
    log = open("platinum_retry.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
