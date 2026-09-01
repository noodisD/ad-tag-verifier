"""Row 26 recheck (longer wait) + nto.pl diagnostic."""
from playwright.sync_api import sync_playwright
import re, time

UA_M = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

def click_consent(page):
    phrases = ['Akceptuję','Akceptuj','Accept all','AKCEPTUJĘ']
    try:
        ok = page.evaluate("""(p) => {
            for (const el of document.querySelectorAll('button,a')) {
                const t=(el.innerText||el.textContent||'').trim().toUpperCase();
                if(p.some(x=>t===x.toUpperCase()||t.startsWith(x.toUpperCase()))){el.click();return t;}
            } return null;
        }""", phrases)
        if ok: print(f"    [consent] {ok}"); return True
    except: pass
    return False

print("="*60)
print("Row 26 recheck + nto.pl diagnostic")
print("="*60)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    # ── Row 26 — Gazeta Mobile, 30s wait ────────────────────────────────────
    print("\n[Row 26 — Gazeta Mobile 900000011]")
    ctx = browser.new_context(viewport={"width":390,"height":844}, locale="pl-PL",
                               user_agent=UA_M, ignore_https_errors=True)
    page = ctx.new_page()
    flags = {"imp": False, "clk": False}
    t_ref = [0.0]

    def on_req26(req, _f=flags, _t=t_ref):
        u = req.url
        if "900000011" not in u: return
        t = time.time() - _t[0] if _t[0] else 0
        if "trackimp" in u and not _f["imp"]:
            _f["imp"] = True; print(f"    [IMP t+{t:.0f}s] {u[:110]}")
        elif "trackclk" in u and not _f["clk"]:
            _f["clk"] = True; print(f"    [CLK t+{t:.0f}s] {u[:110]}")

    page.on("request", on_req26)
    page.goto("https://kobieta.gazeta.pl/kobieta/0,0.html?google_preview=PLACEHOLDER&iu=90000002&gdfp_req=1&lineItemId=9000000363&creativeId=900000043021",
              wait_until="domcontentloaded", timeout=25000)
    t_ref[0] = time.time()
    page.bring_to_front()
    time.sleep(4); click_consent(page); time.sleep(30)  # 30s wait
    print(f"  imp={flags['imp']} clk={flags['clk']}")
    print(f"  >> {'PASS' if flags['imp'] and flags['clk'] else 'IMP ONLY' if flags['imp'] else 'NO TAG'}")
    page.close(); ctx.close()

    # ── nto.pl diagnostic — all doubleclick/ad requests ─────────────────────
    print("\n[nto.pl diagnostic — row 38, capture all ad requests]")
    ctx2 = browser.new_context(viewport={"width":390,"height":844}, locale="pl-PL",
                                user_agent=UA_M, ignore_https_errors=True)
    pg2 = ctx2.new_page()
    all_ads = []
    def on_nto(req):
        u = req.url
        if any(d in u for d in ['doubleclick','dc_trk','googletag','pubads','adform',
                                  'adquery','adnxs','rubiconproject','openx','3lift']):
            all_ads.append(u[:120])
    pg2.on("request", on_nto)

    pg2.goto("https://nto.pl/niebo-nad-paczkowem-zaplonie-kolorami-znamy-program-xii-aeropikniku-i-balonowego-pucharu-polski/ar/c1p2-90000005?google_preview=PLACEHOLDER&iu=900000062&gdfp_req=1&lineItemId=9000000750&creativeId=900000087053",
            wait_until="domcontentloaded", timeout=25000)
    pg2.bring_to_front(); time.sleep(4); click_consent(pg2); time.sleep(12)

    print(f"  Total ad-related requests: {len(all_ads)}")
    cm360_reqs = [u for u in all_ads if 'dc_trk_aid' in u]
    print(f"  CM360 trackimp/trackclk requests: {len(cm360_reqs)}")
    for u in cm360_reqs[:5]:
        print(f"    {u}")
    if not cm360_reqs:
        print("  [Googletag/GAM requests:]")
        gam_reqs = [u for u in all_ads if 'googletag' in u or 'pubads' in u or 'doubleclick.net/gampad' in u]
        for u in gam_reqs[:8]:
            print(f"    {u[:120]}")

    pg2.close(); ctx2.close()
    browser.close()

print("\nDone.")
