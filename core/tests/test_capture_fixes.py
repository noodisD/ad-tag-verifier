"""Three capture behaviours found auditing a BNP Paribas run (2026-10-01).

* a banner served as an <img> inside a tiny <a> was invisible to the click-through
  finder, so four banners that fire and click correctly were reported untested;
* the vision fallback only ever looked at the first screen of the page;
* a preview that had already served the campaign was reloaded anyway, and the
  reload drew a Cloudflare bot challenge that the click and IAS checks then ran on.
"""
import pytest

from core.capture import strategies


# ── the vision fallback looks past the first screen ──────────────────────

class _Page:
    """Just enough page for _ask_where: a scrollable document and screenshots."""

    def __init__(self, height=3000, y=0):
        self.height, self.y, self.scrolled = height, y, []

    def evaluate(self, script, *args):
        if "scrollHeight" in script:
            return self.height
        if "scrollY" in script:
            return self.y
        if "scrollTo" in script:
            self.y = args[0]
            self.scrolled.append(args[0])
            return None

    def screenshot(self, type="png"):
        return b"png@%d" % self.y


def _settings():
    return {"vision": object(), "advertiser": "BankClient",
            "viewport": {"width": 1400, "height": 900}}


def test_the_model_is_shown_every_screen_until_it_finds_the_creative(monkeypatch):
    seen = []

    def locate(eye, shot, advertiser, viewport, why=None):
        seen.append(shot)
        return ({"x": 900, "y": 300, "w": 160, "h": 600, "confidence": 0.95, "reason": ""}
                if len(seen) == 3 else None)

    monkeypatch.setattr(strategies.creative_click, "locate", locate)
    monkeypatch.setattr(strategies.time, "sleep", lambda s: None)
    page, meta = _Page(), {"events": []}
    box = strategies._ask_where(page, _settings(), meta, "1")
    assert box["w"] == 160
    assert len(seen) == 3                      # stopped as soon as it was found
    assert page.y == page.scrolled[-1]         # and the page stays where the banner is
    assert any("screen 3 of" in e for e in meta["events"])


def test_when_nothing_is_found_the_page_goes_back_and_the_log_says_how_far_it_looked(monkeypatch):
    monkeypatch.setattr(strategies.creative_click, "locate", lambda *a, **k: None)
    monkeypatch.setattr(strategies.time, "sleep", lambda s: None)
    page, meta = _Page(), {"events": []}
    assert strategies._ask_where(page, _settings(), meta, "1", _again=False) is None
    assert page.y == 0
    assert "looked through" in meta["events"][-1]


def test_the_search_is_bounded(monkeypatch):
    calls = []
    monkeypatch.setattr(strategies.creative_click, "locate",
                        lambda *a, **k: calls.append(1))
    monkeypatch.setattr(strategies.time, "sleep", lambda s: None)
    strategies._ask_where(_Page(height=90000), _settings(), {"events": []}, "1", _again=False)
    assert len(calls) == strategies.MAX_SCREENS


def test_a_short_page_is_one_screenshot(monkeypatch):
    calls = []
    monkeypatch.setattr(strategies.creative_click, "locate",
                        lambda *a, **k: calls.append(1))
    monkeypatch.setattr(strategies.time, "sleep", lambda s: None)
    strategies._ask_where(_Page(height=800), _settings(), {"events": []}, "1", _again=False)
    assert len(calls) == 1


# ── a preview that already served is not reloaded ────────────────────────

class _Recorder:
    def __init__(self, fired):
        self.fired = set(fired)

    def has(self, kind=None, ident=None, vendor=None, fired_only=True):
        return ident in self.fired

    def wait_for(self, predicate, timeout, poll=0.5):
        return predicate()


class _Nav:
    def __init__(self):
        self.gotos = 0

    def goto(self, url, **kw):
        self.gotos += 1


def _drive(monkeypatch, fired, **target):
    monkeypatch.setattr(strategies.consent, "accept", lambda *a, **k: None)
    monkeypatch.setattr(strategies, "_scroll", lambda *a, **k: None)
    monkeypatch.setattr(strategies, "_wait_for_impression", lambda *a, **k: True)
    monkeypatch.setattr(strategies, "_click_target_id", lambda *a, **k: (None, False))
    monkeypatch.setattr(strategies.time, "sleep", lambda s: None)
    page, meta = _Nav(), {"events": []}
    strategies.gam_preview(page, None, _Recorder(fired), {"poll_interval": 0}, meta,
                           {"url": "https://pub.example/?google_preview=x", **target})
    return page.gotos, meta["events"]


def test_a_campaign_that_served_on_the_first_load_is_not_reloaded(monkeypatch):
    gotos, events = _drive(monkeypatch, {"457906462"}, wait_for=["457906462", "457793365"])
    assert gotos == 1
    assert any("not reloading" in e for e in events)


def test_a_page_that_did_not_serve_ours_is_still_reloaded(monkeypatch):
    """The second load exists because some previews only render on it."""
    gotos, _ = _drive(monkeypatch, {"428251046"}, wait_for=["457906462"])
    assert gotos == 2


def test_without_a_sheet_the_old_two_loads_stay(monkeypatch):
    gotos, _ = _drive(monkeypatch, set())
    assert gotos == 2


def test_an_explicit_expected_id_counts_too(monkeypatch):
    gotos, _ = _drive(monkeypatch, {"90194589"}, expected_id="90194589")
    assert gotos == 1


# ── the banner inside a tiny link ────────────────────────────────────────

@pytest.fixture(scope="module")
def browser_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:           # Chromium not installed on this machine
            pytest.skip(f"no chromium: {type(e).__name__}")
        page = b.new_page(viewport={"width": 1400, "height": 900})
        yield page
        b.close()


PREVIEW_LINK = ('<div style="padding:40px"><a target="_blank" '
                'href="https://delivery.clickonometrics.pl/campaign=1/click/2/previewclick.html?&redir=" '
                'style="display:inline-block;width:160px;height:17px">'
                '<img style="display:block;width:160px;height:600px;background:#0a0" alt=""></a></div>')


def test_the_banner_inside_a_tiny_link_is_found_by_its_image(browser_page):
    """Measured on a clickonometrics preview: the <a> is 160x17, the banner in
    it 160x600. Judging the anchor alone refused it as too small."""
    browser_page.set_content(PREVIEW_LINK)
    el, box = strategies._clickthrough_element(browser_page)
    assert el is not None
    assert (round(box["width"]), round(box["height"])) == (160, 600)


def test_an_unrelated_link_is_not_taken_for_the_creative(browser_page):
    browser_page.set_content('<a href="https://example.org/article" '
                             'style="display:block;width:400px;height:300px">story</a>')
    el, box = strategies._clickthrough_element(browser_page)
    assert el is None and box is None


def test_a_normal_click_tracker_link_still_works(browser_page):
    browser_page.set_content('<a href="https://track.adform.net/C/?bn=1" '
                             'style="display:block;width:300px;height:250px">ad</a>')
    el, box = strategies._clickthrough_element(browser_page)
    assert el is not None and round(box["width"]) == 300


# ── a late load event is not a lost run ──────────────────────────────────

class TimeoutError(Exception):          # same __name__ as Playwright's
    pass


def test_a_page_whose_load_event_is_late_is_carried_on_with():
    """kobieta.gazeta.pl: one of six identical tests came back as an error with
    no result, although the page was up and every ad had been requested."""
    class Slow:
        def goto(self, *a, **k):
            raise TimeoutError("Page.goto: Timeout 60000ms exceeded.")
    meta = {"events": []}
    strategies._goto(Slow(), "https://pub.example/", meta)        # must not raise
    assert "carrying on" in meta["events"][0]


def test_a_refused_connection_still_fails():
    class Refused:
        def goto(self, *a, **k):
            raise RuntimeError("net::ERR_CONNECTION_REFUSED")
    with pytest.raises(RuntimeError):
        strategies._goto(Refused(), "https://pub.example/", {"events": []})


# ── navigation_click judges the campaign, not the first advertiser ────────

class _Beacons:
    def __init__(self, *fired):
        self.beacons = [{"kind": "impression", "evidence": "fired", "id": i} for i in fired]

    def has(self, kind=None, ident=None, vendor=None, fired_only=True):
        return any(b["kind"] == kind and (ident is None or b["id"] == ident) for b in self.beacons)


def test_a_foreign_impression_is_not_the_campaigns():
    """On a portal carrying several interstitials the loop used to stop at the
    first impression of anyone."""
    rec = _Beacons("428251046")
    assert strategies._campaign_fired(rec, None, {"457781885"}) is False
    assert strategies._campaign_fired(_Beacons("457781885"), None, {"457781885"}) is True


def test_with_an_explicit_id_that_id_decides():
    assert strategies._campaign_fired(_Beacons("1"), "2", {"1"}) is False
    assert strategies._campaign_fired(_Beacons("2"), "2", set()) is True


def test_without_a_sheet_any_impression_still_counts():
    assert strategies._campaign_fired(_Beacons("9"), None, set()) is True
    assert strategies._campaign_fired(_Beacons(), None, set()) is False


def test_the_click_is_judged_against_the_id_that_fired():
    """Recorded on kobieta.wp.pl: the click tracked placement 457781885, the
    sheet's own, and was reported "unattributed" because the run had been
    given no single id to expect."""
    rec = _Beacons("428251046", "457781885")
    assert strategies._aim_id(rec, None, {"457781885", "457781882"}) == "457781885"
    assert strategies._aim_id(rec, "7", {"457781885"}) == "7"
    assert strategies._aim_id(_Beacons("1"), None, {"457781885"}) is None


WALLPAPER = ('<body style="margin:0"><a id="skin" href="https://csr.example/clk" '
             'style="position:absolute;left:0;top:0;width:1000px;height:700px;display:block"></a>'
             '<div style="position:absolute;left:200px;top:0;width:600px;height:700px;background:#fff">article</div>'
             '</body>')


def test_a_wallpaper_anchor_is_clicked_where_it_is_on_top(browser_page):
    """Onet screening: the click-through anchor covers the whole page, so its
    centre sits under the article column and a click there hits the article."""
    browser_page.set_content(WALLPAPER)
    pt = strategies._hittable_point(browser_page.query_selector("#skin"))
    assert pt is not None
    assert not 200 <= pt[0] <= 800                    # outside the article column
    top = browser_page.evaluate("([x, y]) => document.elementFromPoint(x, y).id", list(pt))
    assert top == "skin"


def test_an_unobstructed_element_is_hittable_at_its_centre(browser_page):
    browser_page.set_content('<a id="a" href="#" style="display:block;width:300px;height:200px"></a>')
    pt = strategies._hittable_point(browser_page.query_selector("#a"))
    assert abs(pt[0] - 150) < 20 and abs(pt[1] - 100) < 20


class _FakeFrame:
    def __init__(self, url, detached=False):
        self.url, self._d = url, detached

    def is_detached(self):
        return self._d


class _FakeFramesPage:
    def __init__(self, frames):
        self.frames = frames


def test_a_frame_with_no_address_is_never_asked_anything():
    """money.pl, headed: an ad iframe still being created never answers
    `evaluate`, which has no timeout — the run sat there for good."""
    from core.capture import consent
    main, ok = _FakeFrame("https://pub.example/"), _FakeFrame("https://ads.example/x")
    page = _FakeFramesPage([main, ok, _FakeFrame(""), _FakeFrame("https://gone.example/", detached=True)])
    assert consent.live_frames(page) == [main, ok]


def test_the_model_gets_a_second_look_when_the_first_pass_finds_nothing(monkeypatch):
    """Its answer on the same page differs from one look to the next."""
    passes = []

    def locate(eye, shot, advertiser, viewport, why=None):
        passes.append(1)
        return ({"x": 0, "y": 100, "w": 300, "h": 250, "confidence": 0.9, "reason": ""}
                if len(passes) > 1 else None)

    monkeypatch.setattr(strategies.creative_click, "locate", locate)
    monkeypatch.setattr(strategies.time, "sleep", lambda s: None)
    box = strategies._ask_where(_Page(height=800), _settings(), {"events": []}, "1")
    assert box and len(passes) == 2
