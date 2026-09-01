"""
Adform tag verification — re-run for failed tests only.
Skips already-passed tests from the previous run.
"""

from playwright.sync_api import sync_playwright
import re, time, sys

# ── Already verified in previous run ─────────────────────────────────────────
ALREADY_PASSED = {
    "WP 1260x600 v1 Samsung":              "[PASS]",
    "SW 300x600 creativeId=900000010417":  "[PASS]",
    "SW 300x600 creativeId=900000013504":  "[PASS]",
    "SW 300x600 creativeId=900000020017":  "[PASS]",
    "SW 750x100 creativeId=900000037935":  "[PASS]",
    "SW 750x100 creativeId=900000020572":  "[PASS]",
    "SW 1180x300 creativeId=900000012625": "[PASS]",
    "SW 1180x300 creativeId=900000036324": "[PASS]",
    "SW 1180x300 creativeId=900000015064": "[PASS]",
    "SW 1180x500 creativeId=900000044522": "[PASS]",
    "SW 1180x500 creativeId=900000037848": "[PASS]",
    "SW 1180x500 creativeId=900000046205": "[PASS]",
}

# ── Test URLs ─────────────────────────────────────────────────────────────────

# WP — need click verification (impressions already confirmed correct)
WP_URLS = [
    ("WP 300x600 v1 Samsung",         90000005,
     "https://www.pudelek.pl/?wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=300x600_v1_samsung&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2FBaner%2F1580928%22%7D%5D&testPos=36"),
    ("WP 600x400 v1 Samsung",         90000006,
     "https://www.wp.pl/?_device=mobile&wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=600x400_v1_samsung&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22200218%2F1458778%2Fiaq%2FBaner%2F1580927%22%7D%5D&testPos=1"),
    ("WP 1260x600 v3 Fashion sklep",   90000007,
     "https://wiadomosci.wp.pl/?wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=Giga_v3_Fsklep&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2FGigaboard%2F1580925%22%7D%5D&testPos=3"),
    ("WP 300x600 v3 Fashion sklep",    90000008,
     "https://www.pudelek.pl/?wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=WP_300x600_v_Fsklep3&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2FBaner%2F1580923%22%7D%5D&testPos=36"),
    ("WP 600x400 v3 Fashion sklep",    90000009,
     "https://www.wp.pl/?_device=mobile&wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=WP_600x400_v_Fsklep3&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22200218%2F1458778%2Fiaq%2FBaner%2F1580924%22%7D%5D&testPos=1"),
    ("WP 1260x600 v5 Luksusowe Marki", 90000010,
     "https://wiadomosci.wp.pl/?wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=Giga_v5_LuxMarki&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2FGigaboard%2F1581616%22%7D%5D&testPos=3"),
    ("WP 300x600 v5 Luksusowe Marki",  90000011,
     "https://www.pudelek.pl/?wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=300x600_v5_LuxMarki&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2FBaner%2F1580935%22%7D%5D&testPos=36"),
    ("WP 600x400 v5 Luksusowe Marki",  90000012,
     "https://www.wp.pl/?_device=mobile&wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=600_400_v5_LuxMarki&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22200218%2F1458778%2Fiaq%2FBaner%2F1581627%22%7D%5D&testPos=1"),
    ("WP 1260x600 v6 Zainwestuj BankClient",  90000013,
     "https://wiadomosci.wp.pl/?wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=Giga_v6_inwestujBankClient&tcidma=%5B%7B%22slot%22%3A%22003%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2FGigaboard%2F1580933%22%7D%5D&testPos=3"),
    ("WP 300x600 v6 Zainwestuj BankClient",   90000014,
     "https://www.pudelek.pl/?wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=300x600_v6_inwestujBankClient&tcidma=%5B%7B%22slot%22%3A%22035%22%2C%22id%22%3A%22200218%2F1458777%2Fiaq%2FBaner%2F1581626%22%7D%5D&testPos=36"),
    ("WP 600x400 v6 Zainwestuj BankClient",   90000015,
     "https://www.wp.pl/?_device=mobile&wfName=271932_3061220_BankClient-cyberbezpieczenstwo_PremiumReach_mix_01&creName=600_400_v6_inwestujBankClient&tcidma=%5B%7B%22slot%22%3A%22001%22%2C%22id%22%3A%22200218%2F1458778%2Fiaq%2FBaner%2F1581628%22%7D%5D&testPos=1"),
]

# SW mobile formats — need mobile viewport
SW_MOBILE_URLS = [
    ("SW 320x100 creativeId=900000041537", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000041537"),
    ("SW 320x100 creativeId=900000044609", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000044609"),
    ("SW 320x100 creativeId=900000020128", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000020128"),
    ("SW 320x160 creativeId=900000010555", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000010555"),
    ("SW 320x160 creativeId=900000044771", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000044771"),
    ("SW 320x160 creativeId=900000039573", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000039573"),
    ("SW 320x320 creativeId=900000011719", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000011719"),
    ("SW 320x320 creativeId=900000036306", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000036306"),
    ("SW 320x320 creativeId=900000045920", None, "https://spidersweb.pl/2023/12/plus-promocje-smartfony-na-swieta-kolejne.html?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000045920"),
    ("SW 320x480 creativeId=900000011818", None, "https://spidersweb.pl/?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000011818"),
    ("SW 320x480 creativeId=900000038649", None, "https://spidersweb.pl/?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000038649"),
    ("SW 320x480 creativeId=900000014503", None, "https://spidersweb.pl/?google_preview=PLACEHOLDER&iu=1042598&gdfp_req=1&lineItemId=9000001609&creativeId=900000014503"),
]

SW_VALID_BNS = {
    "320x100": {90000017, 90000018, 90000019},
    "320x160": {90000020, 90000021, 90000022},
    "320x320": {90000023, 90000024, 90000025},
    "320x480": {90000026, 90000027, 90000028},
}


def extract_bn(url):
    m = re.search(r'bn=(\d+)', url)
    return int(m.group(1)) if m else None


def banner_size_from_label(label):
    m = re.search(r'(\d{3,4})x(\d{3,4})', label)
    return (int(m.group(1)), int(m.group(2))) if m else None


# ── Consent ───────────────────────────────────────────────────────────────────

CONSENT_SELECTORS = [
    "button:has-text('Akceptuj wszystkie')", "button:has-text('Akceptuj wszystko')",
    "button:has-text('Akceptuj')",           "button:has-text('Akceptuję')",
    "button:has-text('Zgadzam się')",        "button:has-text('Zgoda')",
    "button:has-text('Accept all')",         "button:has-text('Accept')",
    "#onetrust-accept-btn-handler",          ".js-accept-all",
    "[class*='accept-all']",
]

def click_consent(page, ms=1200):
    for sel in CONSENT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=ms):
                btn.click()
                print(f"    [consent] {sel}")
                return True
        except Exception:
            pass
    return False

def setup_consent(ctx, urls):
    for url in urls:
        page = ctx.new_page()
        try:
            print(f"  [consent] {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.bring_to_front()
            time.sleep(3)
            if click_consent(page, ms=2000):
                try: page.wait_for_load_state("domcontentloaded", timeout=8000)
                except: pass
                time.sleep(2)
                print(f"  [consent] done")
            else:
                print(f"  [consent] no popup")
        except Exception as e:
            print(f"  [consent] error: {e}")
        finally:
            page.close()


# ── Scroll until ad fires ─────────────────────────────────────────────────────

def scroll_until_ad(page, impression_bns, click_bns, step=250, pause=1.2, max_scrolls=100):
    for _ in range(max_scrolls):
        if impression_bns or click_bns:
            time.sleep(1.5)
            return True
        scroll_pos = page.evaluate("window.pageYOffset + document.documentElement.clientHeight") or 0
        page_h = page.evaluate("document.body.scrollHeight") or 20000
        if scroll_pos >= page_h:
            break
        try: page.evaluate(f"window.scrollBy(0, {step})")
        except: pass
        time.sleep(pause)
    return bool(impression_bns or click_bns)


# ── Click banner via mouse coordinates + context-level listener ───────────────

def attempt_banner_click(page, ctx, click_bns, expected_bn, banner_size=None):
    """
    Find the ad iframe by size, click its center with page.mouse.click(),
    and capture the resulting /C/?bn= request via context-level listener
    (catches requests from new tabs too).
    """
    ctx_clicks = []

    def on_ctx(req):
        u = req.url
        if 'adform.net' in u and '/C/' in u:
            bn = extract_bn(u)
            if bn and bn not in ctx_clicks:
                ctx_clicks.append(bn)
                print(f"    [CLK-ctx] bn={bn}")

    ctx.on("request", on_ctx)

    try:
        iframes = page.locator("iframe").all()
        for el in iframes:
            try:
                bb = el.bounding_box()
                if not bb:
                    continue
                # Skip tracking pixels and tiny iframes
                if bb['width'] < 80 or bb['height'] < 50:
                    continue
                # Filter by expected size if known
                if banner_size:
                    w, h = banner_size
                    if abs(bb['width'] - w) > 80 or abs(bb['height'] - h) > 80:
                        continue

                # Scroll banner into viewport centre
                el.scroll_into_view_if_needed()
                time.sleep(0.4)
                bb = el.bounding_box()
                if not bb:
                    continue

                cx = bb['x'] + bb['width'] / 2
                cy = bb['y'] + bb['height'] / 2
                print(f"    [click] mouse.click({cx:.0f},{cy:.0f})  iframe {bb['width']:.0f}x{bb['height']:.0f}")
                page.mouse.click(cx, cy)
                time.sleep(4)

                click_bns.extend(ctx_clicks)
                return
            except Exception:
                pass

        print(f"    [click] no matching iframe found (size={banner_size})")
    finally:
        ctx.remove_listener("request", on_ctx)

    click_bns.extend(ctx_clicks)


# ── Core check ────────────────────────────────────────────────────────────────

def check_url(ctx, label, expected_bn, url, valid_bns=None):
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

    # Inline consent fallback
    if click_consent(page, ms=1500):
        try: page.wait_for_load_state("domcontentloaded", timeout=8000)
        except: pass
        t_ref[0] = time.time()
        impression_bns.clear()
        click_bns.clear()

    time.sleep(1.5)
    scroll_until_ad(page, impression_bns, click_bns)

    # DOM scan for Adform click URLs in accessible frames
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

    # Coordinate-based click if impression found but no click yet
    if impression_bns and not click_bns:
        size = banner_size_from_label(label)
        attempt_banner_click(page, ctx, click_bns, expected_bn, banner_size=size)

    page.close()

    imp_unique = list(set(impression_bns))
    clk_unique = list(set(click_bns))

    if valid_bns:
        imp_ok = bool(imp_unique and (set(imp_unique) & valid_bns))
        clk_ok = bool(clk_unique and (set(clk_unique) & valid_bns))
        expected_str = "{" + ", ".join(str(b) for b in sorted(valid_bns)) + "}"
    else:
        imp_ok = expected_bn in imp_unique if imp_unique else False
        clk_ok = expected_bn in clk_unique if clk_unique else False
        expected_str = str(expected_bn)

    status = ("[PASS]"                    if (imp_ok and clk_ok) else
              "[IMP OK / CLICK MISSING]"  if (imp_ok and not clk_ok) else
              "[FAIL - wrong bn]"         if (imp_unique or clk_unique) else
              "[NO AD FIRED]")

    print(f"  {status}")
    print(f"    Expected  : {expected_str}")
    print(f"    Impression: {imp_unique or 'none'}")
    print(f"    Click     : {clk_unique or 'none'}")
    return status


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # Desktop context for WP
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900}, locale="pl-PL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        # Mobile context for SW 320x* formats
        mobile_ctx = browser.new_context(
            viewport={"width": 390, "height": 844}, locale="pl-PL",
            user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"
        )

        print("\n[=== Consent Setup ===]")
        setup_consent(ctx, ["https://www.wp.pl/", "https://www.pudelek.pl/",
                             "https://wiadomosci.wp.pl/"])
        setup_consent(mobile_ctx, ["https://spidersweb.pl/"])

        results = dict(ALREADY_PASSED)  # seed with already-passed results

        # ── WP click re-verification ─────────────────────────────────────────
        print("\n" + "="*60)
        print("WP — Click Re-verification (impressions already confirmed)")
        print("="*60)
        for label, expected_bn, url in WP_URLS:
            print(f"\n[{label}]")
            results[label] = check_url(ctx, label, expected_bn, url)

        # ── SW mobile formats ─────────────────────────────────────────────────
        print("\n" + "="*60)
        print("Spider's Web — Mobile formats (390x844 viewport)")
        print("="*60)
        for label, _, url in SW_MOBILE_URLS:
            size = next((s for s in SW_VALID_BNS if s in label), None)
            valid = SW_VALID_BNS.get(size)
            print(f"\n[{label}]")
            results[label] = check_url(mobile_ctx, label, None, url, valid_bns=valid)

        browser.close()

        # ── Full summary (all 35 URLs) ────────────────────────────────────────
        ALL_LABELS = (
            ["WP 1260x600 v1 Samsung",
             "WP 300x600 v1 Samsung", "WP 600x400 v1 Samsung",
             "WP 1260x600 v3 Fashion sklep",
             "WP 300x600 v3 Fashion sklep", "WP 600x400 v3 Fashion sklep",
             "WP 1260x600 v5 Luksusowe Marki",
             "WP 300x600 v5 Luksusowe Marki", "WP 600x400 v5 Luksusowe Marki",
             "WP 1260x600 v6 Zainwestuj BankClient",
             "WP 300x600 v6 Zainwestuj BankClient", "WP 600x400 v6 Zainwestuj BankClient"] +
            [l for l, _, _ in SW_MOBILE_URLS] +
            [l for l in ALREADY_PASSED if l.startswith("SW")]
        )

        print("\n" + "="*60)
        print("FINAL SUMMARY")
        print("="*60)
        for label in ALL_LABELS:
            status = results.get(label, "[NOT TESTED]")
            print(f"  {status:<35} {label}")

        passed = sum(1 for s in results.values() if s == "[PASS]")
        imp_ok = sum(1 for s in results.values() if "IMP OK" in s or s == "[PASS]")
        total  = len(ALL_LABELS)
        print(f"\n{passed}/{total} fully verified (impression + click)")
        print(f"{imp_ok}/{total} impressions verified OK")
        print("impressions verified OK")   # sentinel for watcher


if __name__ == "__main__":
    log = open("adform_results.txt", "w", encoding="utf-8", buffering=1)
    class Tee:
        def __init__(self, *s): self.s = s
        def write(self, d): [x.write(d) for x in self.s]
        def flush(self): [x.flush() for x in self.s]
    sys.stdout = Tee(sys.__stdout__, log)
    run()
    log.close()
