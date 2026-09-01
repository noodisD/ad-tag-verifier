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

CONSENT_PHRASES = ["Akceptuję", "Akceptuj wszystkie", "Akceptuj", "Zgadzam się", "Accept all"]
CONSENT_SELECTORS = ["#onetrust-accept-btn-handler", "[class*='accept']", "button.sp_choice_type_11"]

PATTERNS = {
    "Adform": {"bn": re.compile(r"bn=(\d+)")},
    "CM360": {
        "dc_trk_aid": re.compile(r"dc_trk_aid=(\d+)"),
        "dc_trk_cid": re.compile(r"dc_trk_cid=(\d+)"),
    },
}


def click_consent(page):
    try:
        clicked = page.evaluate(
            """(phrases) => {
                for (const b of document.querySelectorAll('button')) {
                    const t = b.innerText.trim();
                    if (phrases.some(p => t === p || t.startsWith(p))) { b.click(); return t; }
                }
                return null;
            }""",
            CONSENT_PHRASES,
        )
        if clicked:
            return True
    except Exception:
        pass
    for sel in CONSENT_SELECTORS:
        try:
            if page.locator(sel).first.is_visible(timeout=800):
                page.locator(sel).first.click()
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

    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="pl-PL")
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
