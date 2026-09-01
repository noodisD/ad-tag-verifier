"""
Shared verification logic: given a tag URL and the ID(s) that should fire
when it loads, open it in a real browser and check.

This is the same technique every verify_*.py script in ../scripts uses —
consent handling, then a cross-frame DOM scan plus a network listener for
the platform's beacon pattern — generalized into one function instead of
copy-pasted per campaign.

Only self-referential checks are supported: the expected ID has to be the
one embedded in the URL itself (Adform bn=, CM360 dc_trk_aid/dc_trk_cid).
An Ad Manager preview URL (iu=/lineItemId=/creativeId=) doesn't carry a
checkable beacon ID of its own — it wraps whichever vendor tag the line
item actually serves, which isn't knowable from the URL alone.
"""

import re
import time

# Publishers gate ad delivery on looking like a real browser; the default
# headless UA gets a page that loads but serves no ads.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Longest / most specific first: WP.pl's "accept and continue" has to win
# over a bare "akceptuję" prefix match.
CONSENT_PHRASES = [
    "akceptuję i przechodzę do serwisu",
    "akceptuj wszystkie i przejdź",
    "akceptuję wszystkie",
    "akceptuj wszystkie",
    "zgadzam się",
    "accept all",
    "akceptuję",
    "akceptuj",
]
CONSENT_SELECTORS = [
    "#didomi-notice-agree-button",
    "#onetrust-accept-btn-handler",
    "[data-st='gdpr-accept']",
    ".rodo-popup-agree",
    "button.sp_choice_type_11",
    "button[class*='accept']",
]

# Matching runs in the page so it can normalize whitespace first: these
# labels carry non-breaking spaces ("AKCEPTUJĘ I PRZECHODZĘ DO SERWISU"),
# which a literal Playwright text selector never matches.
_CONSENT_JS = """(phrases) => {
    const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    const els = document.querySelectorAll(
        "button, a[role=button], div[role=button], [class*=accept], [id*=accept]");
    for (const p of phrases) {
        for (const b of els) {
            const t = norm(b.innerText);
            if (t === p || t.startsWith(p)) { b.click(); return b.innerText.trim(); }
        }
    }
    return null;
}"""

PATTERNS = {
    "Adform": {"bn": re.compile(r"bn=(\d+)")},
    "CM360": {
        "dc_trk_aid": re.compile(r"dc_trk_aid=(\d+)"),
        "dc_trk_cid": re.compile(r"dc_trk_cid=(\d+)"),
    },
}


def click_consent(page, settle=3.0):
    """Dismiss the consent wall, on the page itself or inside a CMP iframe.

    The wall is script-rendered after load, so this waits before looking:
    checking straight after `goto` reliably finds nothing, and the page is
    then left in a state where no ad tag ever fires — which reads as "no
    tags implemented" rather than "we never got past the consent screen".
    """
    time.sleep(settle)
    for target in [page] + list(page.frames):
        try:
            clicked = target.evaluate(_CONSENT_JS, CONSENT_PHRASES)
            if clicked:
                time.sleep(2)
                return True
        except Exception:
            pass
    for target in [page] + list(page.frames):
        for sel in CONSENT_SELECTORS:
            try:
                btn = target.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click()
                    time.sleep(2)
                    return True
            except Exception:
                pass
    return False


def deep_dom_scan(page, patterns):
    """Scan every frame's full HTML source for each pattern."""
    found = {k: set() for k in patterns}
    for frame in page.frames:
        try:
            html = frame.content()
        except Exception:
            continue
        for k, rx in patterns.items():
            for m in rx.finditer(html):
                found[k].add(m.group(1))
    return found


# ── Vendor discovery ─────────────────────────────────────────────────────
#
# What a live page can actually be asked: "which ad tags fired here?" — with
# no expected value supplied. Adform and CM360 are the serving tags; ABT
# Shield and DoubleVerify are measurement/verification vendors that ride
# alongside them. All four are recorded the same way, and which ones matter
# is a decision made later, on the client.

VENDOR_PATTERNS = {
    "Adform": {
        "domain": "adform.net",
        "fields": {"bn": re.compile(r"[?&;]bn=(\d+)")},
    },
    "CM360": {
        "domain": "doubleclick.net/ddm/track",
        "fields": {
            "dc_trk_aid": re.compile(r"dc_trk_aid=(\d+)"),
            "dc_trk_cid": re.compile(r"dc_trk_cid=(\d+)"),
            "site_placement": re.compile(r"ddm/track\w*/(N[\w.]+)/(B[\d.]+)"),
        },
    },
    "ABT Shield": {
        "domain": "abtshield.com",
        "fields": {
            "o": re.compile(r"[?&]o=(\d+)"),
            "sid": re.compile(r"[?&]sid=([^&\s\"']+)"),
        },
    },
    "DoubleVerify": {
        # Config params ride in the fragment on the bootstrap script
        # (dvbm.js#cmp=…&plc=…) and in the query string on the visit/event
        # calls, so every separator class here has to include "#".
        "domain": "doubleverify.com",
        "fields": {
            "cmp": re.compile(r"[?&#]cmp=(\d+)"),
            "plc": re.compile(r"[?&#]plc=(\d+)"),
            "advid": re.compile(r"[?&#]advid=(\d+)"),
            "sid": re.compile(r"[?&#]sid=(\d+)"),
        },
    },
}

URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>()\\]+")


def discover_target(browser, url, timeout_s=30):
    """Open a test page and record every ad tag that actually fires on it.

    Discovery, not verification: nothing is compared against an expected
    value here, because at this stage there isn't one — the page is the
    source of truth for what is actually implemented. Comparing that against
    a trafficking sheet is a separate step that happens afterwards.
    """
    hits = {}

    def record(u):
        low = u.lower()
        for vendor, spec in VENDOR_PATTERNS.items():
            if spec["domain"] not in low:
                continue
            bucket = hits.setdefault(vendor, {})
            for field, rx in spec["fields"].items():
                for m in rx.finditer(u):
                    bucket.setdefault(field, set()).add("/".join(g for g in m.groups() if g))

    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="pl-PL", user_agent=UA)
    page = ctx.new_page()
    page.on("request", lambda req: record(req.url))

    status_code = None
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
        status_code = resp.status if resp else None
        click_consent(page)
        time.sleep(2)
        for _ in range(5):
            try:
                page.evaluate("window.scrollBy(0, 400)")
            except Exception:
                pass
            time.sleep(1.2)
        time.sleep(1)
        # Network capture catches most beacons, but a tag that is written
        # into the markup and never requested (or fired inside a frame that
        # finished before the listener attached) only shows up in the DOM.
        for frame in page.frames:
            try:
                html = frame.content()
            except Exception:
                continue
            for m in URL_IN_TEXT.finditer(html):
                record(m.group(0))
    except Exception as e:
        ctx.close()
        return {"status": "error", "detail": str(e)[:200]}

    ctx.close()
    vendors = {v: {f: sorted(vals) for f, vals in fields.items()} for v, fields in hits.items()}
    return {
        "status": "done" if vendors else "none",
        "vendors": vendors,
        "http_status": status_code,
    }


def verify_target(browser, target, timeout_s=25):
    """target: {platform, url, expected: {<field>: '<id>', ...}}

    The URL being loaded already contains the expected ID (that's what makes
    it self-referential), so the outbound navigation request trivially
    contains it too — counting that would make every syntactically valid
    URL "pass" regardless of whether the ad server recognizes the campaign.
    Navigation requests (the URL itself and any redirect hops it takes) are
    therefore excluded from the match; only a *subsequent* request — a
    beacon actually fired by the page — or the resulting DOM counts as
    confirmation.
    """
    platform = target["platform"]
    url = target["url"]
    expected = target["expected"]
    patterns = PATTERNS.get(platform)
    if not patterns:
        return {"status": "error", "detail": "platform not self-verifiable: " + str(platform)}

    network_hits = {k: set() for k in patterns}

    def on_request(req):
        if req.is_navigation_request():
            return
        u = req.url
        for k, rx in patterns.items():
            m = rx.search(u)
            if m:
                network_hits[k].add(m.group(1))

    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="pl-PL", user_agent=UA)
    page = ctx.new_page()
    page.on("request", on_request)

    status_code = None
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
        status_code = resp.status if resp else None
        click_consent(page)
        time.sleep(2)
        for _ in range(5):
            try:
                page.evaluate("window.scrollBy(0, 400)")
            except Exception:
                pass
            time.sleep(1)
        dom_hits = deep_dom_scan(page, patterns)
    except Exception as e:
        ctx.close()
        return {"status": "error", "detail": str(e)[:200]}

    ctx.close()

    observed = {k: sorted(network_hits[k] | dom_hits.get(k, set())) for k in patterns}
    ok = all(v in observed.get(k, []) for k, v in expected.items())
    result = {"status": "pass" if ok else "fail", "observed": observed, "expected": expected, "http_status": status_code}
    if not ok:
        result["detail"] = (
            "loaded (HTTP " + str(status_code) + ") but the expected ID never reappeared in a "
            "follow-up request or the page content — only in the URL you gave it"
        )
    return result
