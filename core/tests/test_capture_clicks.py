"""Clicks that stay on the creative under test, and on the test page.

dziennik.pl, 2026-10-09: with none of the sheet's impressions fired, the run
clicked the first Ad Manager link on the page anyway, at the frame-local centre
of a 300x250 — (150,124) on the page, the site's WIADOMOŚCI menu item — and
went on to search for the creative, scan the DOM and take its screenshot on
wiadomosci.dziennik.pl. A foreign full-screen interstitial (z-index 2147483647,
up from ~16s to ~34s) took clicks meant for the campaign's billboard, and on
money.pl the model would not point at a 300x250 that had fired an Adform id
the sheet does not book.
"""
from urllib.parse import urlparse

import pytest

from core.analyze import vendors
from core.capture import session, strategies


# ── which links may be clicked ────────────────────────────────────────────

SHEET = ("90571110", "90565344", "90484739")


@pytest.mark.parametrize("href", [
    # Ad Manager hands the tracker over inside adurl=, encoded once…
    "https://adclick.g.doubleclick.net/pcs/click?xai=AK&adurl=https%3A%2F%2Ftrack.adform.net"
    "%2FC%2F%3Fbn%3D90484739",
    # …or twice
    "https://adclick.g.doubleclick.net/pcs/click?xai=AK&adurl=https%253A%252F%252Ftrack.adform.net"
    "%252FC%252F%253Fbn%253D90571110",
    "https://track.adform.net/C/?bn=90565344;C=0",
])
def test_a_link_carrying_a_sheet_id_is_ours(href):
    assert strategies._href_is_ours(href, SHEET) is True


def test_a_link_carrying_another_id_is_not_whatever_the_host():
    href = ("https://adclick.g.doubleclick.net/pcs/click?xai=AK&adurl=https%3A%2F%2F"
            "track.adform.net%2FC%2F%3Fbn%3D999")
    assert strategies._href_is_ours(href, SHEET) is False
    assert strategies._href_is_ours(href, SHEET, strict=False) is False


def test_an_ad_manager_link_with_no_id_is_not_taken_on_trust():
    """It is on every Ad Manager ad on the page — the dziennik.pl stray click."""
    href = "https://adclick.g.doubleclick.net/pcs/click?xai=AK&adurl=https://www.example.pl/"
    assert strategies._href_is_ours(href, SHEET) is False
    # …unless the creative is known to be on the page and has no frame.
    assert strategies._href_is_ours(href, SHEET, strict=False) is True


def test_a_redirector_with_no_readable_id_is_still_taken():
    """24 confirmed BNP clicks came through clickonometrics' preview link,
    which only reaches CM360's trackclk by a 302."""
    href = "https://delivery.clickonometrics.pl/campaign=52980/click/508323/previewclick.html?&redir="
    assert strategies._href_is_ours(href, ("457786509",)) is True


def test_an_id_in_a_shape_no_rule_reads_is_found_but_not_inside_a_longer_number():
    clk = "https://ad.doubleclick.net/ddm/clk/583914220;457786509;x"
    assert strategies._href_is_ours(clk, ("457786509",)) is True
    assert strategies._href_is_ours("https://x.example/c?cb=14577865091", ("457786509",)) is False


def test_the_sheets_vendor_is_told_by_the_shape_of_its_ids():
    assert strategies._sheet_vendors(["90571110"]) == {"Adform"}
    assert strategies._sheet_vendors(["457786509", "90571110", "abc"]) == {"Adform", "CM360"}


# ── what the click aims at ────────────────────────────────────────────────

class _Rec:
    def __init__(self, beacons=(), frames=None, t0=None):
        self.beacons = list(beacons)
        self.frames = frames or {}
        if t0 is not None:
            self.t0 = t0

    def impression_frame(self, ident=None):
        if isinstance(ident, str):
            return self.frames.get(ident)
        for i in ident or ():
            if i in self.frames:
                return self.frames[i]
        return None


def _imp(ident, vendor="Adform"):
    return {"kind": vendors.IMPRESSION, "evidence": "fired", "vendor": vendor, "id": ident}


def _clk(ident, vendor="Adform"):
    return {"kind": vendors.CLICK, "evidence": "fired", "vendor": vendor, "id": ident}


def _settings(**kw):
    s = {"viewport": {"width": 1400, "height": 900}, "click": True,
         "vision": None, "advertiser": None, "run_budget": 380}
    s.update(kw)
    return s


def test_with_no_booked_impression_no_frame_is_taken_for_ours(monkeypatch):
    """The sheet's ids as a tuple: the first impression of anyone is not a
    handle on the campaign's creative (dziennik.pl clicked the pre-roll's
    CM360 frame), so only links carrying one of the ids are looked for."""
    asked = {}

    def nope(*a, **k):
        raise AssertionError("no frame is ours when none of ours fired")

    monkeypatch.setattr(strategies, "_creative_frame", nope)
    monkeypatch.setattr(strategies, "_clickthrough_element",
                        lambda page, ids=None, strict=True: asked.update(ids=ids, strict=strict)
                        or (None, None))
    monkeypatch.setattr(strategies, "_wait_out_layer", lambda *a, **k: True)
    monkeypatch.setattr(strategies, "_ask_where", lambda *a, **k: None)
    meta = {"events": []}
    strategies._click_creative(object(), None, _Rec(), _settings(), meta, ("1", "2"))
    assert asked == {"ids": ("1", "2"), "strict": True}
    assert meta["events"][-1] == "click skipped: no clickable creative frame found"


def test_a_single_expected_id_holds_the_links_to_it(monkeypatch):
    calls = []
    monkeypatch.setattr(strategies, "_clickthrough_element",
                        lambda page, ids=None, strict=True: calls.append((ids, strict))
                        or (None, None))
    # Its impression never fired: no evidence the creative is here at all.
    strategies._creative_frame(_Rec(), object(), "90571110")
    # It fired from the page itself, which has no frame to walk up to.
    monkeypatch.setattr(strategies, "_frame_box", lambda fr: (None, None))
    strategies._creative_frame(_Rec(frames={"90571110": "main"}), object(), "90571110")
    # No sheet at all: as it always was.
    strategies._creative_frame(_Rec(), object(), None)
    assert calls == [(["90571110"], True), (["90571110"], False), (None, True)]


def test_a_click_that_took_the_tab_away_for_good_ends_the_clicking(monkeypatch):
    def click(page, ctx, rec, settings, meta, el, box, expected, since, source="frame"):
        meta["click_result"] = "none"
        meta["navigated_away"] = {"t": 1, "url": "https://elsewhere.example/", "returned": False}
        return "clicked"

    monkeypatch.setattr(strategies, "_creative_frame", lambda *a: ("el", {"x": 0}))
    monkeypatch.setattr(strategies, "_wait_out_layer", lambda *a, **k: True)
    monkeypatch.setattr(strategies, "_click_element", click)
    monkeypatch.setattr(strategies, "_ask_where",
                        lambda *a, **k: pytest.fail("the vision search would look at another site"))
    strategies._click_creative(object(), None, _Rec(), _settings(), {"events": []}, "90571110")


# ── the frames of unbooked impressions ────────────────────────────────────

def _unbooked(monkeypatch, beacons, sheet=("90565344", "90571110"), confirm=None, t0=None):
    clicked = []

    def click(page, ctx, rec, settings, meta, el, box, ident, since, source="frame"):
        clicked.append((ident, source))
        meta["click_result"] = "confirmed" if ident == confirm else "none"
        return "clicked"

    monkeypatch.setattr(strategies, "_frame_box", lambda fr: (fr, {"width": 300, "height": 250}))
    monkeypatch.setattr(strategies, "_click_element", click)
    monkeypatch.setattr(strategies, "_wait_out_layer", lambda *a, **k: True)
    rec = _Rec(beacons, frames={b["id"]: f"frame-{b['id']}" for b in beacons}, t0=t0)
    meta = {"events": []}
    deadline = strategies._deadline(rec, _settings())
    tried = strategies._click_unbooked(object(), None, rec, _settings(), meta, sheet, deadline)
    return tried, clicked, meta


def test_unbooked_frames_of_the_sheets_vendor_are_tried_at_most_twice(monkeypatch):
    """money.pl: the creatives fired Adform 90626723-26, ids the sheet lacks."""
    beacons = [_imp("455988298", "CM360"),           # another vendor: somebody else's
               _imp("90565344"),                     # booked: not this path's business
               _imp("90626723"), _imp("90626724"), _imp("90626725")]
    tried, clicked, _ = _unbooked(monkeypatch, beacons)
    assert tried == 2
    assert clicked == [("90626723", "unbooked"), ("90626724", "unbooked")]


def test_a_confirmed_unbooked_click_says_whose_it_was(monkeypatch):
    beacons = [_imp("90626723"), _imp("90626724")]
    tried, clicked, meta = _unbooked(monkeypatch, beacons, confirm="90626723")
    assert clicked == [("90626723", "unbooked")]
    assert meta["click_target_id"] == "90626723"
    assert "which the sheet does not book" in meta["events"][-1]


def test_an_unbooked_id_whose_click_already_tracked_is_not_clicked_again(monkeypatch):
    """The model's click landed on 90626723 and its click beacon carried it:
    the beacon has answered, and the report reads that answer."""
    beacons = [_imp("90626723"), _clk("90626723")]
    tried, clicked, _ = _unbooked(monkeypatch, beacons)
    assert (tried, clicked) == (0, [])


def test_no_unbooked_clicks_without_the_time_for_them(monkeypatch):
    import time
    tried, clicked, meta = _unbooked(monkeypatch, [_imp("90626723")], t0=time.time() - 350)
    assert (tried, clicked) == (0, [])
    assert "no time left" in meta["events"][-1]


# ── the run's budget ──────────────────────────────────────────────────────

def test_a_click_with_no_time_left_is_not_started():
    import time
    meta = {"events": []}
    rec = _Rec(t0=time.time() - 370)
    assert strategies._click_element(object(), None, rec, _settings(), meta, None,
                                     {"x": 0, "y": 0, "width": 300, "height": 250},
                                     "1", 0) == "no-time"
    strategies._clicked_at(object(), None, rec, _settings(), meta, "1", 10, 10, 0, "model")
    assert meta["events"] == ["click skipped: the run is out of time for this page"] * 2


# ── the vision search starts at the top ──────────────────────────────────

class _ScrolledPage:
    def __init__(self, y):
        self.y, self.shots = y, []

    def evaluate(self, script, *args):
        if "scrollHeight" in script:
            return 6000
        if "scrollY" in script:
            return self.y
        if "scrollTo" in script:
            self.y = args[0]

    def screenshot(self, type="png"):
        self.shots.append(self.y)
        return b"png"


def test_the_vision_search_starts_at_the_top_wherever_the_page_was(monkeypatch):
    """A wait that ended deep in the page used to hide everything above it from
    the model — screenings and billboards are on the first screen."""
    monkeypatch.setattr(strategies.creative_click, "locate", lambda *a, **k: None)
    monkeypatch.setattr(strategies, "_pause", lambda page, s: None)
    page = _ScrolledPage(3000)
    strategies._ask_where(page, _settings(vision=object(), advertiser="BankClient"),
                          {"events": []}, "1", _again=False)
    assert page.shots[0] == 0
    assert page.shots == sorted(page.shots)


# ── live ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:           # Chromium not installed on this machine
            pytest.skip(f"no chromium: {type(e).__name__}")
        yield b
        b.close()


def _ctx(browser, pages):
    """A context whose sites answer locally: nothing leaves the machine."""
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})

    def serve(route):
        body = pages.get(urlparse(route.request.url).path, "<p>landing</p>")
        route.fulfill(status=200, content_type="text/html", body=body)

    ctx.route("https://pub.example/**", serve)
    ctx.route("https://track.adform.net/**",
              lambda r: r.fulfill(status=200, content_type="text/html", body="<p>advertiser</p>"))
    return ctx


class _QuickTabs:
    """The context, with a shorter wait for a tab that a same-tab click will
    never open."""

    def __init__(self, ctx):
        self.ctx = ctx

    def expect_page(self, timeout=None):
        return self.ctx.expect_page(timeout=1500)


@pytest.fixture
def quick_confirm(monkeypatch):
    """One look for the click beacon instead of eight seconds of them."""
    def once(recorder, meta, expected_id, since, source):
        verdict, ident = strategies.creative_click.click_confirmed(recorder, expected_id, since)
        meta["click_result"] = verdict
        strategies._log(meta, f"click result {verdict} {ident} ({source})")
    monkeypatch.setattr(strategies, "_confirm_click", once)


def _recorded(ctx, url):
    rec = session.Recorder()
    rec.attach(ctx)
    page = ctx.new_page()
    rec.bind(page)
    page.goto(url)
    return rec, page


GAM_ADS = """<body style="margin:0">
<a id="foreign" href="https://adclick.g.doubleclick.net/pcs/click?xai=1&adurl=https%3A%2F%2Ftrack.adform.net%2FC%2F%3Fbn%3D999"
   style="display:block;width:970px;height:250px">another advertiser</a>
<a id="plain" href="https://adclick.g.doubleclick.net/pcs/click?xai=2&adurl=https://shop.example/"
   style="display:block;width:750px;height:200px">no id</a>
<a id="ours" href="https://adclick.g.doubleclick.net/pcs/click?xai=3&adurl=https%3A%2F%2Ftrack.adform.net%2FC%2F%3Fbn%3D90571110"
   style="display:block;width:300px;height:250px">ours</a></body>"""


def test_with_a_sheet_only_the_link_carrying_its_id_is_found(browser):
    ctx = _ctx(browser, {"/a": GAM_ADS})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        el, box = strategies._clickthrough_element(page, ids=SHEET)
        assert el.evaluate("e => e.id") == "ours"
        el, _ = strategies._clickthrough_element(page, ids=("1",))
        assert el is None
        # Known to be on the page: an id-less link is a candidate, a foreign one never.
        el, _ = strategies._clickthrough_element(page, ids=("1",), strict=False)
        assert el.evaluate("e => e.id") == "plain"
        # No sheet: the largest click-tracker link, as it always was.
        el, _ = strategies._clickthrough_element(page)
        assert el.evaluate("e => e.id") == "foreign"
    finally:
        ctx.close()


# clickonometrics' own preview: the banner is an <img> in a 160x17 link whose
# href carries no id a vendor rule reads (see test_capture_fixes).
PREVIEW_LINK = ('<div style="padding:40px"><a target="_blank" '
                'href="https://delivery.clickonometrics.pl/campaign=1/click/2/previewclick.html?&redir=" '
                'style="display:inline-block;width:160px;height:17px">'
                '<img style="display:block;width:160px;height:600px;background:#0a0" alt=""></a></div>')


def test_the_clickonometrics_preview_link_is_still_found_with_a_sheet(browser):
    ctx = _ctx(browser, {"/a": PREVIEW_LINK})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        el, box = strategies._clickthrough_element(page, ids=("457786509",))
        assert el is not None and round(box["height"]) == 600
    finally:
        ctx.close()


def test_a_point_found_inside_an_ad_frame_is_put_back_into_page_coordinates(browser):
    """The frame-local centre of a 300x250 is (150,125); fed to the page as is,
    it was dziennik.pl's WIADOMOŚCI menu item."""
    ctx = _ctx(browser, {"/a": (
        '<body style="margin:0"><a href="/wiadomosci" style="position:absolute;left:100px;'
        'top:100px;width:120px;height:50px">WIADOMOŚCI</a>'
        '<iframe src="/ad" style="position:absolute;left:300px;top:200px;width:300px;'
        'height:250px;border:0"></iframe></body>'),
        "/ad": '<body style="margin:0"><a id="ad" href="https://track.adform.net/C/?bn=1" '
               'style="display:block;width:300px;height:250px">ad</a></body>'})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        frame = next(f for f in page.frames if f.url.endswith("/ad"))
        el = frame.wait_for_selector("#ad")
        x, y, dx, dy = strategies._hittable_spot(el)
        assert 300 <= x <= 600 and 200 <= y <= 450, (x, y)
        assert abs(dx - 150) < 15 and abs(dy - 125) < 15
        assert page.evaluate("([x, y]) => document.elementFromPoint(x, y).tagName",
                             [x, y]) == "IFRAME"
    finally:
        ctx.close()


COVERED = """<body style="margin:0">
<a id="ad" href="https://track.adform.net/C/?bn=90571110" onclick="window.adHit=1"
   style="position:absolute;left:100px;top:100px;width:300px;height:250px">ad</a>
<div id="layer" onclick="window.layerHit=1"
     style="position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.5)"></div>
<script>window.closeAfter && setTimeout(() => document.getElementById('layer').remove(),
                                         window.closeAfter);</script></body>"""


def test_a_covered_creative_is_refused_never_clicked_through_the_cover(browser):
    """The element click is refused when something sits over it; clicking the
    same spot by coordinates anyway hit dziennik.pl's foreign interstitial."""
    ctx = _ctx(browser, {"/a": COVERED})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        el = page.query_selector("#ad")
        why = strategies._press(page, el, None, True)
        assert why and "intercepts pointer events" in why
        assert page.evaluate("[!!window.adHit, !!window.layerHit]") == [False, False]
    finally:
        ctx.close()


def test_a_foreign_full_screen_layer_is_waited_out(browser):
    ctx = _ctx(browser, {"/a": COVERED.replace("window.closeAfter &&", "")
                         .replace("window.closeAfter)", "1500)")})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        meta = {"events": []}
        assert strategies._wait_out_layer(page, _settings(), meta, page.query_selector("#ad"))
        assert "z=2147483647" in meta["events"][0] and "waiting up to 20s" in meta["events"][0]
        assert meta["events"][1].strip().startswith("it closed after")
        assert meta["foreign_layer_wait_s"] < 5
        assert strategies._foreign_layer(page) is None
    finally:
        ctx.close()


def test_a_layer_holding_the_creative_is_the_creative_not_an_obstacle(browser):
    """A full-screen interstitial the sheet books is what is being clicked."""
    ctx = _ctx(browser, {"/a": (
        '<body style="margin:0"><div id="layer" style="position:fixed;inset:0;'
        'z-index:2147483647"><a id="ad" href="https://track.adform.net/C/?bn=1" '
        'style="display:block;width:100%;height:100%">interstitial</a></div></body>')})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        assert strategies._foreign_layer(page, page.query_selector("#ad")) is None
        assert strategies._foreign_layer(page) is not None
    finally:
        ctx.close()


def test_a_layer_that_lets_clicks_through_is_no_obstacle(browser):
    ctx = _ctx(browser, {"/a": (
        '<body><div style="position:fixed;inset:0;z-index:2147483647;'
        'pointer-events:none"></div></body>')})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        assert strategies._foreign_layer(page) is None
    finally:
        ctx.close()


def test_a_layer_that_stays_up_is_given_its_time_and_no_more(browser, monkeypatch):
    monkeypatch.setattr(strategies, "FOREIGN_LAYER_WAIT_S", 2)
    ctx = _ctx(browser, {"/a": COVERED})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        meta = {"events": []}
        assert strategies._wait_out_layer(page, _settings(), meta) is False
        assert "still up" in meta["events"][-1]
        # Spent: the next click does not wait again.
        assert strategies._wait_out_layer(page, _settings(), meta) is False
        assert "no time left to wait" in meta["events"][-1]
    finally:
        ctx.close()


# ── leaving the test page ─────────────────────────────────────────────────

NAV = ('<body style="margin:0"><a id="nav" href="/wiadomosci" style="position:absolute;'
       'left:100px;top:100px;width:120px;height:50px">WIADOMOŚCI</a>'
       '<a id="ad" href="https://track.adform.net/C/?bn=90571110;C=0" target="{target}" '
       'style="position:absolute;left:400px;top:300px;width:300px;height:250px">ad</a></body>')


def test_a_stray_click_that_navigates_the_test_tab_is_undone(browser, quick_confirm):
    ctx = _ctx(browser, {"/a": NAV.format(target="_self"), "/wiadomosci": "<h1>news</h1>"})
    try:
        rec, page = _recorded(ctx, "https://pub.example/a")
        meta = {"events": []}
        strategies._clicked_at(page, _QuickTabs(ctx), rec, _settings(), meta, SHEET,
                               160, 125, len(rec.beacons), "model")
        assert page.url == "https://pub.example/a"
        assert meta["navigated_away"]["returned"] is True
        assert meta["navigated_away"]["url"] == "https://pub.example/wiadomosci"
        assert any("took the test tab itself away" in e and "went back" in e
                   for e in meta["events"])
    finally:
        ctx.close()


def test_a_same_tab_click_through_is_kept_and_the_tab_comes_back(browser, quick_confirm):
    ctx = _ctx(browser, {"/a": NAV.format(target="_self")})
    try:
        rec, page = _recorded(ctx, "https://pub.example/a")
        meta = {"events": []}
        strategies._click_creative(page, _QuickTabs(ctx), rec, _settings(), meta, SHEET)
        assert meta["click_result"] == "confirmed"
        assert meta["landing"].startswith("https://track.adform.net/C/?bn=90571110")
        assert page.url == "https://pub.example/a"
        assert any("opened in the test tab itself" in e for e in meta["events"])
    finally:
        ctx.close()


def test_a_click_through_in_a_new_tab_is_the_normal_case(browser, quick_confirm):
    import time
    ctx = _ctx(browser, {"/a": NAV.format(target="_blank")})
    try:
        rec, page = _recorded(ctx, "https://pub.example/a")
        # Little of the budget left, which also keeps the new tab's landing
        # watch to its shortest.
        rec.t0 = time.time() - 352
        meta = {"events": []}
        strategies._click_creative(page, ctx, rec, _settings(), meta, SHEET)
        assert meta["click_result"] == "confirmed"
        assert "navigated_away" not in meta
        assert any(e.startswith("landing -> https://track.adform.net/C/") for e in meta["events"])
        assert page.url == "https://pub.example/a"
    finally:
        ctx.close()


def test_a_url_rewritten_in_place_is_not_leaving(browser):
    """Players and endless articles rewrite their URL with pushState while the
    document stays put; going back there would undo the page itself."""
    ctx = _ctx(browser, {"/a": "<p>article</p>"})
    try:
        page = ctx.new_page()
        page.goto("https://pub.example/a")
        watch = strategies._TabWatch(page)
        page.evaluate("history.pushState({}, '', '/a/next-article')")
        assert watch.left(settle=1) is None
        watch.stop()

        watch = strategies._TabWatch(page)
        page.evaluate("setTimeout(() => { location.href = '/b'; }, 0)")
        page.wait_for_url("https://pub.example/b")
        assert watch.left(settle=1) == "https://pub.example/b"
        watch.stop()
    finally:
        ctx.close()
