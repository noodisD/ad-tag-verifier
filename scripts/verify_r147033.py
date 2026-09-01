from playwright.sync_api import sync_playwright
import re, time, sys

CONSENT_SELECTORS = [
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj')",
    "button:has-text('Zgadzam się')", "[class*='accept']", "[class*='agree']",
    "button.sp_choice_type_11",
]

def extract_bn(url):
    m = re.search(r'bn=(\d+)', url)
    return int(m.group(1)) if m else None

def click_consent(page, ms=1500):
    for sel in CONSENT_SELECTORS:
        try:
            if page.locator(sel).first.is_visible(timeout=ms):
                page.locator(sel).first.click()
                print(f"  [consent] {sel}")
                return True
        except: pass
    for frame in page.frames:
        if frame == page.main_frame: continue
        for sel in CONSENT_SELECTORS:
            try:
                if frame.locator(sel).first.is_visible(timeout=400):
                    frame.locator(sel).first.click()
                    print(f"  [consent-iframe] {sel}")
                    return True
            except: pass
    return False

log = open("r147033_result.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
    )

    # Consent setup
    setup = ctx.new_page()
    setup.goto("https://kobieta.onet.pl/?ress=mobile", wait_until="domcontentloaded", timeout=25000)
    setup.bring_to_front()
    time.sleep(6)
    if click_consent(setup, ms=3000):
        time.sleep(2)
        print("  [consent-setup] done")
    else:
        print("  [consent-setup] no popup")
    setup.close()

    imps, clks, t_ref = [], [], [0.0]

    def on_req(req):
        u = req.url
        if "adform.net" not in u: return
        bn = extract_bn(u)
        if not bn: return
        t = time.time() - t_ref[0]
        if "adfserve" in u or "1x1inv" in u:
            if bn not in imps:
                imps.append(bn)
                print(f"  [IMP] bn={bn}  t+{t:.1f}s")
        elif "/C/" in u:
            if bn not in clks:
                clks.append(bn)
                print(f"  [CLK] bn={bn}  t+{t:.1f}s")

    page = ctx.new_page()
    page.on("request", on_req)
    print("\n[RASP BB_320x100 r147033 — retest]")
    page.goto("https://kobieta.onet.pl/?ress=mobile#adbeta=r147033!slot.bottom-bar",
              wait_until="domcontentloaded", timeout=35000)
    t_ref[0] = time.time()
    page.bring_to_front()
    if click_consent(page, ms=2000):
        t_ref[0] = time.time(); imps.clear(); clks.clear()
    time.sleep(1.5)
    for _ in range(100):
        if imps: time.sleep(1.5); break
        try: page.evaluate("window.scrollBy(0, 250)")
        except: pass
        time.sleep(1.2)
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
                if bn and bn not in clks:
                    clks.append(bn)
                    print(f"  [DOM-CLK] bn={bn}")
        except: pass
    page.close()
    browser.close()

    print(f"\nImpression : {list(set(imps)) or 'none'}")
    print(f"Click      : {list(set(clks)) or 'none'}")
    if imps:
        print(f"STATUS     : [PASS]" if clks else "[IMP OK / CLICK MISSING]")
    else:
        print("STATUS     : [NO AD FIRED]")

log.close()
