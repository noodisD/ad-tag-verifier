"""Retest: RASP BIM2 Desktop screening — fresh desktop context"""
from playwright.sync_api import sync_playwright
import re, time, sys

URL = "https://kobieta.onet.pl/#adbeta=r147304!slot.top"
EXPECTED_AID = 900000015

log = open("rasp_desktop_retest.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Zgadzam się','Accept all','Accept'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked:
            print(f"    [consent-js] '{clicked}'")
            return True
    except: pass
    for sel in ["[class*='accept']", "#onetrust-accept-btn-handler", "button.sp_choice_type_11",
                "[class*='agree']", "button:has-text('Akceptuj')"]:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click()
                print(f"    [consent-sel] {sel}")
                return True
        except: pass
    for frame in page.frames:
        if frame == page.main_frame: continue
        try:
            clicked = frame.evaluate("""() => {
                const phrases = ['Akceptuję','Akceptuj','Zgadzam się','Accept all'];
                for (const b of document.querySelectorAll('button')) {
                    const t = b.innerText.trim();
                    if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
                }
                return null;
            }""")
            if clicked:
                print(f"    [consent-iframe] '{clicked}'")
                return True
        except: pass
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # Fresh consent setup
    setup = ctx.new_page()
    setup.goto("https://kobieta.onet.pl/", wait_until="domcontentloaded", timeout=25000)
    setup.bring_to_front()
    time.sleep(8)
    if click_consent(setup):
        time.sleep(2)
        print("  [consent-setup] done")
    setup.close()

    imp_aids = []
    t_ref = [0.0]

    def on_req(req):
        u = req.url
        t = time.time() - t_ref[0] if t_ref[0] else 0
        if 'doubleclick.net/ddm/trackimp' in u:
            m = re.search(r'dc_trk_aid=(\d+)', u)
            if m:
                aid = int(m.group(1))
                if aid not in imp_aids:
                    imp_aids.append(aid)
                    print(f"    [IMP] dc_trk_aid={aid}  t+{t:.1f}s")
        elif 'doubleclick.net/ddm/trackclk' in u:
            m = re.search(r'dc_trk_aid=(\d+)', u)
            if m:
                print(f"    [CLK-net] dc_trk_aid={m.group(1)}  t+{t:.1f}s")

    page = ctx.new_page()
    page.on("request", on_req)

    print(f"\n[RASP BIM2 D screening — retest]")
    print(f"URL: {URL}\n")

    page.goto(URL, wait_until="domcontentloaded", timeout=35000)
    t_ref[0] = time.time()
    page.bring_to_front()
    click_consent(page)
    time.sleep(3)

    # Extended scroll
    for i in range(120):
        if imp_aids:
            time.sleep(2)
            break
        try: page.evaluate("window.scrollBy(0, 300)")
        except: pass
        time.sleep(1.2)
        if i % 20 == 0 and i > 0:
            print(f"  [scroll] step {i}, no ad yet...")

    time.sleep(2)

    # DOM scan
    clk_aids = set()
    for frame in page.frames:
        try:
            aids = frame.evaluate(r"""() => {
                const aids = new Set();
                document.querySelectorAll('[href],[src],[onclick]').forEach(el => {
                    ['href','src','onclick'].forEach(a => {
                        const v = decodeURIComponent(el.getAttribute(a) || '');
                        if (v.includes('trackclk')) {
                            const n = v.match(/dc_trk_aid=(\d+)/);
                            if (n) aids.add(parseInt(n[1]));
                        }
                    });
                });
                document.querySelectorAll('a').forEach(a => {
                    const h = decodeURIComponent(a.href || '');
                    if (h.includes('trackclk')) {
                        const n = h.match(/dc_trk_aid=(\d+)/);
                        if (n) aids.add(parseInt(n[1]));
                    }
                });
                return [...aids];
            }""")
            for a in aids: clk_aids.add(a)
        except: pass

    for a in clk_aids:
        print(f"    [DOM-CLK] dc_trk_aid={a}")

    page.close()
    browser.close()

    imp_ok = EXPECTED_AID in set(imp_aids)
    clk_ok = EXPECTED_AID in clk_aids
    if imp_ok and clk_ok:
        status = "[PASS]"
    elif imp_ok:
        status = "[IMP OK / CLICK MISSING]"
    elif imp_aids or clk_aids:
        status = f"[FAIL - wrong aid]"
    else:
        status = "[NO TAG FIRED]"

    print(f"\n  Status   : {status}")
    print(f"  Expected : dc_trk_aid={EXPECTED_AID}")
    print(f"  IMP aids : {list(set(imp_aids)) or 'none'}")
    print(f"  CLK aids : {sorted(clk_aids) or 'none'}")

log.close()
