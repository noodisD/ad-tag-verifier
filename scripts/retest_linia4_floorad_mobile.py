"""Retest: Linia4 Floorad mobile — bn expected from BN_LINIA4 set"""
from playwright.sync_api import sync_playwright
import re, time, sys

URL = "https://www.eska.pl/news/?force_mobile=1&google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000196&creativeId=900000022012"
BN_LINIA4 = {90000003, 90000004, 90000005, 90000006, 90000007, 90000008, 90000009}

log = open("linia4_floorad_mobile_retest.txt", "w", encoding="utf-8", buffering=1)
class Tee:
    def __init__(self, *s): self.s = s
    def write(self, d): [x.write(d) for x in self.s]
    def flush(self): [x.flush() for x in self.s]
sys.stdout = Tee(sys.__stdout__, log)

def click_consent(page):
    try:
        clicked = page.evaluate("""() => {
            const phrases = ['Akceptuję','Akceptuj wszystkie','Akceptuj','Zgadzam się'];
            for (const b of document.querySelectorAll('button')) {
                const t = b.innerText.trim();
                if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
            }
            return null;
        }""")
        if clicked:
            print(f"  [consent-js] '{clicked}'")
            return True
    except: pass
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
    )

    # Consent setup
    setup = ctx.new_page()
    setup.goto("https://www.eska.pl/?force_mobile=1", wait_until="domcontentloaded", timeout=25000)
    setup.bring_to_front()
    time.sleep(8)
    click_consent(setup)
    time.sleep(2)
    setup.close()

    impression_bns, click_bns, abt_orders = [], [], []
    t_ref = [0.0]

    def on_req(req):
        u = req.url
        t = time.time() - t_ref[0] if t_ref[0] else 0
        if 'adform.net' in u:
            m = re.search(r'bn=(\d+)', u)
            bn = int(m.group(1)) if m else None
            if 'adfserve' in u or '1x1inv' in u:
                if bn and bn not in impression_bns:
                    impression_bns.append(bn)
                    print(f"  [IMP] bn={bn}  t+{t:.1f}s")
            elif '/C/' in u:
                if bn and bn not in click_bns:
                    click_bns.append(bn)
                    print(f"  [CLK-net] bn={bn}  t+{t:.1f}s")
            # Log ALL adform for diagnosis
            print(f"  [ADFORM] {u[:120]}")
        if 'abtshield.com' in u:
            m = re.search(r'o=(\d+)', u)
            order = m.group(1) if m else None
            if order and order not in abt_orders:
                abt_orders.append(order)
                print(f"  [ABT] o={order}  t+{t:.1f}s")

    page = ctx.new_page()
    page.on("request", on_req)
    print(f"\n[Linia4 Floorad mobile — retest]")
    print(f"URL: {URL}\n")
    page.goto(URL, wait_until="domcontentloaded", timeout=35000)
    t_ref[0] = time.time()
    page.bring_to_front()
    click_consent(page)
    time.sleep(2)

    # Extended scroll — 150 steps
    for i in range(150):
        if impression_bns:
            time.sleep(2)
            break
        try: page.evaluate("window.scrollBy(0, 250)")
        except: pass
        time.sleep(1.2)
        if i % 20 == 0 and i > 0:
            print(f"  [scroll] step {i}, no ad yet...")

    time.sleep(3)

    # DOM scan
    print("\n  --- DOM adform scan ---")
    for frame in page.frames:
        try:
            results = frame.evaluate(r"""() => {
                const hits = new Set();
                const re = /adform\.net[^\s"'<>]*/gi;
                document.querySelectorAll('*').forEach(el => {
                    ['href','src','onclick'].forEach(a => {
                        const v = el.getAttribute(a);
                        if (v) { const m = v.match(re); if (m) m.forEach(x => hits.add(a+': '+x)); }
                    });
                });
                document.querySelectorAll('a').forEach(a => {
                    if (a.href && a.href.includes('adform')) hits.add('a.href: '+a.href.slice(0,200));
                    const d = decodeURIComponent(a.href||'');
                    if (d.includes('adform')) hits.add('decoded: '+d.slice(0,200));
                });
                return [...hits];
            }""")
            for r in results:
                print(f"    [frame {frame.url[:50]}] {r[:150]}")
        except: pass

    page.close()
    browser.close()

    imp_ok = bool(set(impression_bns) & BN_LINIA4)
    clk_ok = bool(set(click_bns) & BN_LINIA4)
    status = ("[PASS]" if imp_ok and clk_ok else
              "[IMP OK / CLICK MISSING]" if imp_ok else
              "[FAIL - wrong bn]" if impression_bns or click_bns else
              "[NO AD FIRED]")

    print(f"\n  Status     : {status}")
    print(f"  Impression : {list(set(impression_bns)) or 'none'}")
    print(f"  Click      : {list(set(click_bns)) or 'none'}")
    print(f"  ABT orders : {sorted(set(abt_orders)) or 'none'}")

log.close()
