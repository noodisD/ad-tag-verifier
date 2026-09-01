"""
THE BANKING CLIENT Ubezpieczenie Dziecko — WP.pl Adform tag verification
Checks both IMP (track.adform.net/adfserve) and CLK (track.adform.net/C/) for all 33 test URLs.
"""

import re, time, urllib.parse, os
from playwright.sync_api import sync_playwright

STATE_FILE = r"./session_state.json"

ACCEPT_SELECTORS = [
    'button:has-text("Akceptuję i przechodzę do serwisu")',
    'button:has-text("Akceptuj wszystkie i przejdź")',
    'button:has-text("Akceptuję wszystkie")',
    'button:has-text("Akceptuj wszystkie")',
    'button:has-text("Akceptuję")',
    '#didomi-notice-agree-button',
    '[data-st="gdpr-accept"]',
    '.rodo-popup-agree',
    'button[class*="accept"]',
    'button[class*="Accept"]',
]

def accept_cookies(page):
    """Click the GDPR consent button on WP.pl pages. Tries main page + all frames."""
    for sel in ACCEPT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
                time.sleep(1.5)
                return True
        except Exception:
            pass
    for frame in page.frames:
        if not frame.url:
            continue
        for sel in ACCEPT_SELECTORS:
            try:
                btn = frame.locator(sel).first
                if btn.is_visible(timeout=500):
                    btn.click()
                    time.sleep(1.5)
                    return True
            except Exception:
                pass
    return False


def setup_cookie_state(pw):
    """One-time: visit wp.pl, accept cookies, save storage state to STATE_FILE."""
    print("[SETUP] Accepting cookies on wp.pl …")
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    browser = pw.chromium.launch(headless=False,
                                  args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                               user_agent=ua, locale="pl-PL")
    page = ctx.new_page()
    page.goto("https://www.wp.pl", wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)
    ok = accept_cookies(page)
    print(f"[SETUP] Cookie accepted: {ok}")
    time.sleep(2)
    ctx.storage_state(path=STATE_FILE)
    print(f"[SETUP] State saved → {STATE_FILE}")
    ctx.close()
    browser.close()

# ─── Expected bn mapping ────────────────────────────────────────────────────
# From WP.pl_21706_THE BANKING CLIENT_Ubezpzycie Excel, sheet Tags
# format: (creative_suffix_in_excel, size) -> bn
# faul=Gips, hejt=Hejt, trampolina=plain CROSS_WP, hulajnoga=Hulajnoga

SIZE_TO_EXCEL_ROW = {
    "160x600":   0,  # Skyscrapper
    "300x250":   1,  # Rectangle
    "300x600":   2,  # HalfPage
    "970x200":   3,  # Wideboard 1
    "970x300":   4,  # Wideboard 2
    "750x100":   5,  # Billboard
    "750x200":   6,  # DoubleBillboard
    "750x300":   7,  # TrippleBillboard
}

# bn base numbers per creative (indexed by SIZE_TO_EXCEL_ROW)
BN_BY_CREATIVE = {
    "Gips":      [90000001, 90000002, 90000003, 90000004, 90000005, 90000006, 90000007, 90000008],
    "plain":     [90000009, 90000010, 90000011, 90000012, 90000013, 90000014, 90000015, 90000016],
    "Hejt":      [90000017, 90000018, 90000019, 90000020, 90000021, 90000022, 90000023, 90000024],
    "Hulajnoga": [90000025, 90000026, 90000027, 90000028, 90000029, 90000030, 90000031, 90000032],
}

def get_expected_bn(creative, size):
    """Return expected Adform bn number for a given creative and size, or None if unknown."""
    grp = creative if creative in BN_BY_CREATIVE else "plain"
    # Normalise size: strip _1/_2 suffix for 750x100 variants
    base_size = re.sub(r'_\d+$', '', size)
    idx = SIZE_TO_EXCEL_ROW.get(base_size)
    if idx is None:
        return None
    return str(BN_BY_CREATIVE[grp][idx])


def build_url(wf_name, cre_name, slot_id, slot_num="3", test_pos="3"):
    tcidma = urllib.parse.quote(f'[{{"slot":"{slot_num}","id":"208166/0/iaq/BanerMC/{slot_id}"}}]')
    wf = urllib.parse.quote(wf_name)
    cre = urllib.parse.quote(cre_name)
    return f"https://film.wp.pl?wfName={wf}&creName={cre}&tcidma={tcidma}&testPos={test_pos}"


WF = "Z-283219 E-3091859 BankClient_Ubezpieczenie dziecko display 08.2025"
_P = "137154_BankClient_kampania_ubezpieczenia_Dziecko_CROSS_WP_"

# ─── All 33 test rows ────────────────────────────────────────────────────────
# (label, creative_group, size_key, slot_id, exact_creName)
# "plain" group has no variant word in creName (just size)
ROWS = [
    # Gips (8)
    ("Gips_160x600",      "Gips",      "160x600",   "1717789", _P+"Gips_160x600"),
    ("Gips_300x250",      "Gips",      "300x250",   "1717790", _P+"Gips_300x250"),
    ("Gips_300x600",      "Gips",      "300x600",   "1717791", _P+"Gips_300x600"),
    ("Gips_750x100_1",    "Gips",      "750x100_1", "1717792", _P+"Gips_750x100_1"),
    ("Gips_750x200",      "Gips",      "750x200",   "1717793", _P+"Gips_750x200"),
    ("Gips_750x300",      "Gips",      "750x300",   "1717794", _P+"Gips_750x300"),
    ("Gips_970x200",      "Gips",      "970x200",   "1717795", _P+"Gips_970x200"),
    ("Gips_970x300",      "Gips",      "970x300",   "1717796", _P+"Gips_970x300"),
    # Plain CROSS_WP — no variant word in creName (9)
    ("plain_160x600",     "plain",     "160x600",   "1719427", _P+"160x600"),
    ("plain_300x250",     "plain",     "300x250",   "1719428", _P+"300x250"),
    ("plain_300x600",     "plain",     "300x600",   "1719429", _P+"300x600"),
    ("plain_750x100_1",   "plain",     "750x100_1", "1719430", _P+"750x100_1"),
    ("plain_750x100_2",   "plain",     "750x100_2", "1719431", _P+"750x100_2"),
    ("plain_750x200",     "plain",     "750x200",   "1719432", _P+"750x200"),
    ("plain_750x300",     "plain",     "750x300",   "1719433", _P+"750x300"),
    ("plain_970x200",     "plain",     "970x200",   "1719434", _P+"970x200"),
    ("plain_970x300",     "plain",     "970x300",   "1719435", _P+"970x300"),
    # Hejt (8)
    ("Hejt_160x600",      "Hejt",      "160x600",   "1719436", _P+"Hejt_160x600"),
    ("Hejt_300x250",      "Hejt",      "300x250",   "1719437", _P+"Hejt_300x250"),
    ("Hejt_300x600",      "Hejt",      "300x600",   "1719438", _P+"Hejt_300x600"),
    ("Hejt_750x100_1",    "Hejt",      "750x100_1", "1719439", _P+"Hejt_750x100_1"),
    ("Hejt_750x200",      "Hejt",      "750x200",   "1719440", _P+"Hejt_750x200"),
    ("Hejt_750x300",      "Hejt",      "750x300",   "1719441", _P+"Hejt_750x300"),
    ("Hejt_970x200",      "Hejt",      "970x200",   "1719442", _P+"Hejt_970x200"),
    ("Hejt_970x300",      "Hejt",      "970x300",   "1719443", _P+"Hejt_970x300"),
    # Hulajnoga (8)
    ("Hulajnoga_160x600",   "Hulajnoga", "160x600",   "1719444", _P+"Hulajnoga_160x600"),
    ("Hulajnoga_300x250",   "Hulajnoga", "300x250",   "1719446", _P+"Hulajnoga_300x250"),
    ("Hulajnoga_300x600",   "Hulajnoga", "300x600",   "1719447", _P+"Hulajnoga_300x600"),
    ("Hulajnoga_750x100_1", "Hulajnoga", "750x100_1", "1719448", _P+"Hulajnoga_750x100_1"),
    ("Hulajnoga_750x200",   "Hulajnoga", "750x200",   "1719449", _P+"Hulajnoga_750x200"),
    ("Hulajnoga_750x300",   "Hulajnoga", "750x300",   "1719450", _P+"Hulajnoga_750x300"),
    ("Hulajnoga_970x200",   "Hulajnoga", "970x200",   "1719451", _P+"Hulajnoga_970x200"),
    ("Hulajnoga_970x300",   "Hulajnoga", "970x300",   "1719452", _P+"Hulajnoga_970x300"),
]


def make_request_listener(flags):
    def on_request(req):
        u = req.url
        if 'track.adform.net/adfserve' in u and '1x1inv=1' in u:
            m = re.search(r'[?&;]bn=(\d+)', u)
            if m and not flags["imp"]:
                flags["imp"] = True
                flags["imp_bn"] = m.group(1)
                flags["imp_url"] = u[:200]
        elif 'track.adform.net/C/' in u:
            m = re.search(r'[?&;]bn=(\d+)', u)
            if m and not flags["clk"]:
                flags["clk"] = True
                flags["clk_bn"] = m.group(1)
                flags["clk_url"] = u[:200]
    return on_request


def try_click_adform(page, flags):
    """Try to click an Adform banner to trigger the CLK pixel."""
    main_base = page.url.split("?")[0].rstrip("/")

    # First: look for clickable links inside non-main frames
    for frame in page.frames:
        fu = (frame.url or "").split("?")[0].rstrip("/")
        if fu == main_base or not frame.url:
            continue
        try:
            # Try Adform click link directly
            locs = [
                frame.locator("a[href*='track.adform.net/C/']"),
                frame.locator("a[href*='adform.net']"),
                frame.locator("a"),
            ]
            for loc in locs:
                try:
                    n = loc.count()
                    if n == 0:
                        continue
                    with page.expect_popup(timeout=5000) as pu:
                        loc.first.click()
                    popup = pu.value
                    popup.on("request", make_request_listener(flags))
                    # Also check the popup URL and redirect chain
                    time.sleep(4)
                    if flags["clk"]:
                        return True
                    # Check popup requests already seen
                    pu_url = popup.url
                    if 'track.adform.net' in pu_url:
                        m = re.search(r'[?&;]bn=(\d+)', pu_url)
                        if m:
                            flags["clk"] = True
                            flags["clk_bn"] = m.group(1)
                            flags["clk_url"] = pu_url[:200]
                            return True
                    try:
                        popup.close()
                    except Exception:
                        pass
                    if flags["clk"]:
                        return True
                except Exception:
                    pass
        except Exception:
            pass

    # Second: try clicking at common banner positions on the main page
    vw, vh = page.viewport_size["width"], page.viewport_size["height"]
    positions = [
        (vw // 2, int(vh * 0.25)),
        (vw // 2, int(vh * 0.40)),
        (vw // 2, int(vh * 0.55)),
        (int(vw * 0.75), int(vh * 0.30)),
    ]
    for x, y in positions:
        try:
            with page.expect_popup(timeout=2000) as pu:
                page.mouse.click(x, y)
            popup = pu.value
            popup.on("request", make_request_listener(flags))
            time.sleep(3)
            if flags["clk"]:
                return True
            try:
                popup.close()
            except Exception:
                pass
        except Exception:
            pass
        if flags["clk"]:
            return True

    return flags["clk"]


def run():
    results = []
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    with sync_playwright() as pw:
        # One-time cookie setup (skipped if state file already exists)
        if not os.path.exists(STATE_FILE):
            setup_cookie_state(pw)

        for label, creative, size_key, slot_id, cre_name in ROWS:
            url = build_url(WF, cre_name, slot_id)
            expected_bn = get_expected_bn(creative, size_key)

            print(f"\n[{label}] slot={slot_id} expected_bn={expected_bn}")
            print(f"  URL: {url[:120]}...")

            flags = {"imp": False, "imp_bn": None, "imp_url": "",
                     "clk": False, "clk_bn": None, "clk_url": ""}

            browser = pw.chromium.launch(headless=False,
                                          args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(
                storage_state=STATE_FILE,
                viewport={"width": 1280, "height": 800},
                user_agent=ua,
                locale="pl-PL",
            )
            page = ctx.new_page()
            page.on("request", make_request_listener(flags))
            ctx.on("request", make_request_listener(flags))

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  [WARN] goto: {e}")

            # Fallback: accept cookies if banner still appears
            time.sleep(2)
            accept_cookies(page)

            # Wait up to 25s for IMP
            t0 = time.time()
            for _ in range(25):
                if flags["imp"]:
                    break
                time.sleep(1)
            t_imp = time.time() - t0

            if flags["imp"]:
                imp_ok = flags["imp_bn"] == expected_bn
                print(f"  IMP: {'OK' if imp_ok else 'WRONG BN'} bn={flags['imp_bn']} expected={expected_bn} t+{t_imp:.0f}s")
                if not imp_ok:
                    print(f"    IMP URL: {flags['imp_url']}")
            else:
                imp_ok = False
                print(f"  IMP: NO TAG after {t_imp:.0f}s")

            # Try CLK
            try_click_adform(page, flags)

            if flags["clk"]:
                clk_ok = flags["clk_bn"] == expected_bn
                print(f"  CLK: {'OK' if clk_ok else 'WRONG BN'} bn={flags['clk_bn']} expected={expected_bn}")
                if not clk_ok:
                    print(f"    CLK URL: {flags['clk_url']}")
            else:
                clk_ok = False
                print(f"  CLK: NO TAG")

            status = "PASS" if (imp_ok and clk_ok) else ("IMP_ONLY" if imp_ok else ("CLK_ONLY" if clk_ok else "FAIL"))
            results.append({
                "label": label, "slot": slot_id, "cre": cre_name, "expected_bn": expected_bn,
                "imp": imp_ok, "imp_bn": flags["imp_bn"],
                "clk": clk_ok, "clk_bn": flags["clk_bn"],
                "status": status,
            })

            ctx.close()
            browser.close()
            time.sleep(2)

    # ─── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"{'Label':<30} {'Slot':<10} {'Exp BN':<12} {'IMP':>6} {'IMP BN':<12} {'CLK':>6} {'CLK BN':<12} {'Status'}")
    print("-" * 80)
    for r in results:
        print(
            f"{r['label']:<30} {r['slot']:<10} {r['expected_bn'] or '?':<12}"
            f" {'OK' if r['imp'] else 'FAIL':>6} {r['imp_bn'] or '-':<12}"
            f" {'OK' if r['clk'] else 'FAIL':>6} {r['clk_bn'] or '-':<12}"
            f" {r['status']}"
        )

    # Write results file
    out_path = r"./bankclient_wp_results.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("THE BANKING CLIENT Ubezpieczenie Dziecko — WP.pl Adform tag verification\n")
        f.write(f"Run: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"{'Label':<30} {'Slot':<10} {'Exp BN':<12} {'IMP':>6} {'IMP BN':<12} {'CLK':>6} {'CLK BN':<12} {'Status'}\n")
        f.write("-" * 100 + "\n")
        for r in results:
            f.write(
                f"{r['label']:<30} {r['slot']:<10} {r['expected_bn'] or '?':<12}"
                f" {'OK' if r['imp'] else 'FAIL':>6} {r['imp_bn'] or '-':<12}"
                f" {'OK' if r['clk'] else 'FAIL':>6} {r['clk_bn'] or '-':<12}"
                f" {r['status']}\n"
            )
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    run()
