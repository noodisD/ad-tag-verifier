"""
Adform tag verification — DV360 preview URLs (BankClient Cyberbezpieczenstwo)
No xlsx comparison — just report what bn= fires for each creative.
"""

from playwright.sync_api import sync_playwright
import re, time, sys

DV360_URLS = [
    ("DV360 336x280",  "xbid.900000010", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000010&ecId=AOgHqNplEpWXac8mvzTGfIWwRw47XS7KN_kbW61Au8jpH-aP2Wdt2m03122IRrG4PldVdTYimcWlC5iLU3pU-QR8BX4wUXrm0w==&eftd=1&dv3b=IIO2_ZwaMMiXiLsC&flexHeight=600&flexWidth=300BankClient_2026-05-15_336x280"),
    ("DV360 750x200",  "xbid.900000023", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000023&ecId=AOgHqNqwjh7z9k10QNW-b9comy39T3o9JTEQE3aLRrifpIRUXK2Ho3rM9QhRHIBRcJ72TK4RzF952Om_5l9kjqbEFzPJ84QmIg==&eftd=1&dv3b=IIO2_ZwaMMiXiLsC&flexHeight=280&flexWidth=336BankClient_2026-05-15_750x200"),
    ("DV360 750x300",  "xbid.900000030", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000030&ecId=AOgHqNo14bGzRLa9fu37hYjQMxXF9AqAu-HhnCToWLAzQkNOsX9WyU7wnxkfeips3fXF2O6v7dNEF8yAqPdweRe9wdJmronVig==&eftd=1&dv3b=IIO2_ZwaMMiXiLsC&flexHeight=200&flexWidth=750BankClient_2026-05-15_750x300"),
    ("DV360 950x200",  "xbid.900000045", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000045&ecId=AOgHqNoYTYAn1Saz0xSUBggNXmcNu7gZYcB0US6j7QbzYg5dt_Poju4kl6fkaLPggyzl8nkZkIOcb1ghXxAdEEndBe9o193JPg==&eftd=1&dv3b=IIO2_ZwaMMiXiLsC&flexHeight=300&flexWidth=750BankClient_2026-05-15_950x200"),
    ("DV360 950x300",  "xbid.900000055", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000055&ecId=AOgHqNrPtjCDc4cNhV0tZTHa_WiZjdU_8AlZEpzWpc5pTNzlp2AvyinVkzhC_RJD4ar1Ia7ekNAu-v9W9S9mRTH5ukP2mCBtdw==&eftd=1&dv3b=IIO2_ZwaMMiXiLsC&flexHeight=200&flexWidth=950BankClient_2026-05-15_950x300"),
    ("DV360 970x300a", "xbid.900000058", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000058&ecId=AOgHqNp36dQDlswyyiWiUuj7UExKJv16l-GWXIbX47qo6v1k8D3YlL1-UT6bx2pPFL_fOtSXyy1H5TvjhQJqBz6LrajE8zRDoA==&eftd=1&dv3b=IIO2_ZwaMMiXiLsC&flexHeight=300&flexWidth=950BankClient_2026-05-15_970x300"),
    ("DV360 970x300b", "xbid.900000060", "https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.900000060&ecId=AOgHqNraFBK6dAM--1W9gffx6nDBCfXMqtFpnpHeW5Ivsyfj-A5HzBp5HSJQIgYqCxcGlaqfnMlJssSuy2sacyQq6iyDS6zrlA==&eftd=1&dv3b=IIO2_ZwaMMiXiLsC&flexHeight=300&flexWidth=970"),
]


def extract_bn(url):
    m = re.search(r'bn=(\d+)', url)
    return int(m.group(1)) if m else None


def check_url(ctx, label, creative_id, url):
    impression_bns = []
    click_bns = []
    t_ref = [0.0]

    def on_req(req):
        u = req.url
        if 'adform.net' not in u:
            return
        bn = extract_bn(u)
        if not bn:
            return
        t = time.time() - t_ref[0] if t_ref[0] else 0
        if 'adfserve' in u or '1x1inv' in u:
            if bn not in impression_bns:
                impression_bns.append(bn)
                print(f"    [IMP] bn={bn}  t+{t:.1f}s")
        elif '/C/' in u:
            if bn not in click_bns:
                click_bns.append(bn)
                print(f"    [CLK-net] bn={bn}  t+{t:.1f}s")

    page = ctx.new_page()
    page.on("request", on_req)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
    except Exception as e:
        print(f"  [load error] {e}")

    t_ref[0] = time.time()
    page.bring_to_front()
    time.sleep(2)

    # Scroll to trigger lazy-loaded content
    for _ in range(20):
        if impression_bns:
            break
        try:
            page.evaluate("window.scrollBy(0, 300)")
        except Exception:
            pass
        time.sleep(1.0)

    time.sleep(2)

    # DOM scan for click URLs across all frames
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
                    print(f"    [DOM-CLK] bn={bn}")
        except Exception:
            pass

    page.close()

    imp_unique = list(set(impression_bns))
    clk_unique = list(set(click_bns))

    if imp_unique and clk_unique:
        status = "[PASS]"
    elif imp_unique:
        status = "[IMP OK / CLICK MISSING]"
    elif clk_unique:
        status = "[CLICK ONLY / NO IMP]"
    else:
        status = "[NO AD FIRED]"

    print(f"  {status}")
    print(f"    creativeId : {creative_id}")
    print(f"    Impression : {imp_unique or 'none'}")
    print(f"    Click      : {clk_unique or 'none'}")
    return status, imp_unique, clk_unique


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="pl-PL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        results = []
        print("\n" + "="*60)
        print("DV360 Preview — BankClient Cyberbezpieczenstwo")
        print("="*60)

        for label, creative_id, url in DV360_URLS:
            print(f"\n[{label}]")
            status, imp, clk = check_url(ctx, label, creative_id, url)
            results.append((label, creative_id, status, imp, clk))

        browser.close()

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for label, cid, status, imp, clk in results:
            print(f"  {status:<35} {label}  |  bn_imp={imp or 'none'}  bn_clk={clk or 'none'}")

        passed  = sum(1 for *_, s, i, c in results if s == "[PASS]")
        imp_ok  = sum(1 for *_, s, i, c in results if i)
        total   = len(results)
        print(f"\n{passed}/{total} fully verified (impression + click)")
        print(f"{imp_ok}/{total} impressions verified OK")


if __name__ == "__main__":
    log = open("dv360_results.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
