"""
Deep click-tag inspection for eska.pl GAM creatives.
Scans all frames for adform.net URLs in: href, onclick, data-*, JS vars, full HTML.
"""
from playwright.sync_api import sync_playwright
import re, time, sys

# One URL per linia to check click tag presence
CHECK_URLS = [
    ("Linia3 Screening desktop", False,
     "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000027674"),
    ("Linia3 Floorad desktop",   False,
     "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000396&creativeId=900000042591"),
    ("Linia4 Screening desktop", False,
     "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000125&creativeId=900000056451"),
    ("Linia4 Floorad desktop",   False,
     "https://www.eska.pl/news/?google_preview=PLACEHOLDER&iu=1014333&gdfp_req=1&lineItemId=9000000396&creativeId=900000042567"),
]

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

def scan_frame_for_adform(frame, label=""):
    found = []
    try:
        results = frame.evaluate(r"""() => {
            const hits = new Set();
            const adformRe = /adform\.net[^\s"'<>]*/gi;

            // 1. All elements — href, onclick, data-* attributes, src
            document.querySelectorAll('*').forEach(el => {
                ['href','src','action','onclick','data-click','data-url',
                 'data-click-url','data-href','data-redirect'].forEach(attr => {
                    const v = el.getAttribute(attr);
                    if (v) { const m = v.match(adformRe); if (m) m.forEach(x => hits.add(attr + ': ' + x)); }
                });
            });

            // 2. Script tag contents
            document.querySelectorAll('script').forEach(s => {
                const m = s.textContent.match(adformRe);
                if (m) m.forEach(x => hits.add('script: ' + x));
            });

            // 3. All link hrefs (catches encoded GAM redirect URLs too)
            document.querySelectorAll('a').forEach(a => {
                const h = a.href || '';
                if (h.includes('adform')) hits.add('a.href: ' + h.slice(0,200));
                // Also check if GAM wraps adform in the click URL
                const enc = decodeURIComponent(h);
                if (enc.includes('adform')) hits.add('a.href(decoded): ' + enc.slice(0,200));
            });

            return [...hits];
        }""")
        for r in results:
            found.append(r)
            print(f"    [{label}] {r[:150]}")
    except Exception as e:
        pass
    return found

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    desktop_ctx = browser.new_context(
        viewport={"width": 1280, "height": 900}, locale="pl-PL",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # Consent setup
    setup = desktop_ctx.new_page()
    setup.goto("https://www.eska.pl/", wait_until="domcontentloaded", timeout=25000)
    setup.bring_to_front()
    time.sleep(8)
    click_consent(setup)
    time.sleep(2)
    setup.close()

    for label, is_mobile, url in CHECK_URLS:
        print(f"\n{'='*60}")
        print(f"[{label}]")
        impression_bns = []
        t_ref = [0.0]

        def on_req(req):
            u = req.url
            if 'adform.net' in u:
                m = re.search(r'bn=(\d+)', u)
                t = time.time() - t_ref[0]
                if 'adfserve' in u or '1x1inv' in u:
                    if m:
                        impression_bns.append(int(m.group(1)))
                        print(f"  [IMP] bn={m.group(1)}  t+{t:.1f}s")
                elif '/C/' in u:
                    print(f"  [CLK-net] bn={m.group(1) if m else '?'}  t+{t:.1f}s  {u[:100]}")

        page = desktop_ctx.new_page()
        page.on("request", on_req)
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        t_ref[0] = time.time()
        page.bring_to_front()
        click_consent(page)
        time.sleep(2)

        # Scroll until impression fires
        for _ in range(60):
            if impression_bns: time.sleep(2); break
            try: page.evaluate("window.scrollBy(0, 300)")
            except: pass
            time.sleep(1.2)

        print(f"\n  --- Adform URL scan across all frames ---")
        any_found = False
        for i, frame in enumerate(page.frames):
            hits = scan_frame_for_adform(frame, f"frame{i} {frame.url[:40]}")
            if hits: any_found = True

        if not any_found:
            print("  [no adform URLs found in DOM/scripts]")

        page.close()

    browser.close()
    print("\nDone.")
