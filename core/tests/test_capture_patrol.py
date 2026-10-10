"""The wait walks the page instead of parking at its top.

dziennik.pl, 2026-10-09: GPT renders a slot below the fold only once it is near
the viewport, and the creative's Adform impression is a call it makes on
render. Ad Manager had already returned the campaign's 1140x600 for bill_top
(y=1234 in a 900px window); the run waited 260s at y=0 and reported the tag as
not firing. Scrolled to, it fired within a second.
"""
import pytest

from core.capture import session, strategies


# ── where the patrol stops ────────────────────────────────────────────────

def test_the_last_screen_of_the_page_is_always_a_stop():
    stops = strategies._patrol_stops(3000, 900, [], 12)
    assert stops[0] == 0
    assert stops[-1] == 2100                   # H - V, or the bottom slot is never shown
    assert all(b - a <= 765 for a, b in zip(stops, stops[1:]))


def test_a_one_screen_preview_is_just_the_top():
    assert strategies._patrol_stops(600, 900, [], 12) == [0]


def test_a_page_with_no_bottom_is_walked_only_so_far():
    """An OLX listing loads more as it is scrolled; a pass has to end."""
    stops = strategies._patrol_stops(90000, 900, [], 12)
    assert len(stops) == 12
    assert stops[-1] == 11 * 765


def test_a_frame_no_screen_shows_whole_gets_a_stop_centred_on_it():
    """bill_top's 1140x600 at y=1234 straddles the 765 and 1530 screens."""
    stops = strategies._patrol_stops(5000, 900, [[1234, 600]], 12)
    assert 1234 + 300 - 450 in stops


def test_a_frame_some_screen_already_shows_adds_nothing():
    assert (strategies._patrol_stops(5000, 900, [[800, 250]], 12)
            == strategies._patrol_stops(5000, 900, [], 12))


def test_a_frame_beyond_the_pass_adds_nothing():
    assert (strategies._patrol_stops(90000, 900, [[50000, 600]], 12)
            == strategies._patrol_stops(90000, 900, [], 12))


@pytest.mark.parametrize("view", [844, 900])
@pytest.mark.parametrize("h", [50, 250, 600])
def test_every_slot_is_at_least_half_on_screen_at_some_stop(view, h):
    stops = strategies._patrol_stops(8000, view, [], 12)
    for y in range(0, 6000, 37):
        best = max(min(y + h, s + view) - max(y, s) for s in stops)
        assert best >= 0.5 * min(h, view), (y, h, view)


# ── the walk itself, on a fake page and a fake clock ──────────────────────

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


class _Page:
    """A scrollable page: `height` may change between passes, `locked` keeps
    it where it is (an interstitial with overflow:hidden on the body)."""

    def __init__(self, clock, height=5000, view=900, locked=False):
        self.clock, self.height, self.view, self.locked = clock, height, view, locked
        self.y, self.scrolls, self.shapes, self._h = 0, [], 0, 0

    def evaluate(self, script, *args):
        if script is strategies._PAGE_SHAPE:
            self.shapes += 1
            self._h = self.height(self.shapes) if callable(self.height) else self.height
            return {"height": self._h, "view": self.view, "ads": []}
        if script is strategies._SCROLL_TO:
            if not self.locked:
                self.y = max(0, min(args[0], self._h - self.view))
            self.scrolls.append((self.clock.now, args[0]))
            return self.y
        if "scrollTo(0, 0)" in script:
            self.y = 0
            self.scrolls.append((self.clock.now, 0))
            return None
        raise AssertionError(f"unexpected script: {script[:60]}")


class _Rec:
    """Fires `ident` once the page has shown [top, top+h] for `hold` seconds —
    the dziennik.pl slot that renders, and fires, only near the viewport."""

    def __init__(self, clock, page, top=None, h=600, hold=0.5, ident="90571110"):
        self.clock, self.page = clock, page
        self.top, self.h, self.hold, self.ident = top, h, hold, ident
        self.fired, self.shown_for = False, 0.0

    def has(self, kind=None, ident=None, vendor=None, fired_only=True):
        return self.fired and ident in (None, self.ident)

    def _tick(self, dt):
        if self.top is None:
            return
        y, v = self.page.y, self.page.view
        if y < self.top + self.h and self.top < y + v:
            self.shown_for += dt
            if self.shown_for >= self.hold:
                self.fired = True
        else:
            self.shown_for = 0.0

    def wait_for(self, predicate, timeout, poll=0.5):
        end = self.clock.now + timeout
        while self.clock.now < end:
            if predicate():
                return True
            dt = min(poll, end - self.clock.now)
            self.clock.now += dt
            self._tick(dt)
        return bool(predicate())


def _settings(**kw):
    s = {"patience": 60, "poll_interval": 0.5, "patrol": True,
         "patrol_dwell": 2, "patrol_screens": 12}
    s.update(kw)
    return s


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(strategies, "time", c)
    return c


def test_the_slot_below_the_fold_fires_once_the_walk_reaches_it(clock):
    page = _Page(clock)
    rec = _Rec(clock, page, top=1234)
    meta = {"events": []}
    ok = strategies._wait_for_impression(rec, _settings(), meta, wait_for=["90571110"],
                                         page=page)
    assert ok is True
    assert [y for _t, y in page.scrolls][:2] == [0, 765]
    assert page.y == 765, "left where it fired, so the click finds it on screen"
    assert meta["patrol"]["fired_at_y"] == 765
    assert any("patrol: fired with the page at y=765" in e for e in meta["events"])
    assert "this campaign's impression seen within 60s" in meta["events"][-1]


def test_every_screen_is_held_for_the_dwell(clock):
    page = _Page(clock, height=4000)
    rec = _Rec(clock, page)                     # never fires
    strategies._wait_for_impression(rec, _settings(patience=30), {"events": []},
                                    wait_for=["1"], page=page)
    times = [t for t, _y in page.scrolls]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps and min(gaps[:-1]) >= 2.0 - 1e-9


def test_when_nothing_fires_the_walk_loops_until_the_patience_and_ends_at_the_top(clock):
    page = _Page(clock, height=3000)
    rec = _Rec(clock, page)
    meta = {"events": []}
    start = clock.now
    ok = strategies._wait_for_impression(rec, _settings(patience=30), meta,
                                         wait_for=["1"], page=page)
    assert ok is False
    assert meta["patrol"]["passes"] >= 2
    assert page.scrolls[-1][1] == 0 and page.y == 0
    assert clock.now - start <= 30 + 2.5
    # Worded as before, so diagnose() still reads it.
    assert "this campaign's impression NOT seen within 30s" in meta["events"][-1]


def test_the_page_is_measured_again_on_every_pass(clock):
    """Slots fill and the page grows; the second pass goes where the first
    could not."""
    page = _Page(clock, height=lambda n: 3000 if n == 1 else 6000)
    rec = _Rec(clock, page)
    strategies._wait_for_impression(rec, _settings(patience=40), {"events": []},
                                    wait_for=["1"], page=page)
    assert max(y for _t, y in page.scrolls) == 6000 - 900


def test_already_fired_means_no_walk(clock):
    page = _Page(clock)
    rec = _Rec(clock, page)
    rec.fired = True
    meta = {"events": []}
    assert strategies._wait_for_impression(rec, _settings(), meta, wait_for=["90571110"],
                                           page=page) is True
    assert page.scrolls == []
    assert "seen within" in meta["events"][-1]


def test_a_page_that_will_not_scroll_is_said_so(clock):
    page = _Page(clock, locked=True)
    meta = {"events": []}
    strategies._wait_for_impression(_Rec(clock, page), _settings(patience=10), meta,
                                    wait_for=["1"], page=page)
    assert meta["patrol"]["stuck"] > 0
    assert any("would not scroll" in e for e in meta["events"])


def test_patrol_off_is_the_old_wait_at_the_top(clock):
    page = _Page(clock)
    meta = {"events": []}
    ok = strategies._wait_for_impression(_Rec(clock, page, top=1234), _settings(patrol=False),
                                         meta, wait_for=["90571110"], page=page)
    assert ok is False and page.scrolls == []
    assert "patrol" not in meta


def test_the_wait_is_cut_to_leave_the_click_time_inside_the_run_budget(clock):
    """dziennik.pl waits 260s; after a 60s goto that would run into the
    backend's 420s kill mid-click, and the kill loses the verdict."""
    page = _Page(clock)
    rec = _Rec(clock, page)
    rec.t0 = clock.now - 220                     # 160s of the 380s budget left
    meta = {"events": []}
    strategies._wait_for_impression(rec, _settings(patience=260, run_budget=380), meta,
                                    wait_for=["1"], page=page)
    assert any("waiting 100s, not 260s" in e for e in meta["events"])
    assert "NOT seen within 100s" in meta["events"][-1]


def test_a_wait_with_room_to_spare_keeps_its_patience(clock):
    page = _Page(clock)
    rec = _Rec(clock, page)
    rec.t0 = clock.now - 20
    meta = {"events": []}
    strategies._wait_for_impression(rec, _settings(patience=60, run_budget=380), meta,
                                    wait_for=["1"], page=page)
    assert "NOT seen within 60s" in meta["events"][-1]
    assert not any("not 60s" in e for e in meta["events"])


# ── the lazy-load pass before the wait ───────────────────────────────────

class _ScrollPage:
    def __init__(self, fail_at=None):
        self.calls, self.fail_at = [], fail_at

    def evaluate(self, script, *args):
        self.calls.append(script)
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise RuntimeError("Execution context was destroyed")


def test_the_lazy_load_pass_always_ends_at_the_top(monkeypatch):
    """It used to return from mid-page when a scroll failed, and a patrol: false
    profile would then have waited wherever that was."""
    monkeypatch.setattr(strategies, "_pause", lambda page, s: None)
    for fail_at in (None, 3):
        page = _ScrollPage(fail_at)
        strategies._scroll(page, {"scroll_passes": 6, "scroll_step": 500})
        assert "scrollTo(0, 0)" in page.calls[-1], fail_at


# ── live: a slot that renders only near the viewport ──────────────────────

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


# A slot at y=1500 in a 900px window whose impression is requested once it is
# in view, as Ad Manager's lazy render does on dziennik.pl.
IN_VIEW_ONLY = """<body style="margin:0;height:6000px">
<div id="slot" style="position:absolute;top:1500px;width:300px;height:250px"></div>
<script>
new IntersectionObserver((es, io) => {
  if (es.some(e => e.isIntersecting)) {
    io.disconnect();
    new Image().src = 'https://track.adform.net/adfserve/?bn=7777777;1x1inv=1';
  }
}).observe(document.getElementById('slot'));
</script></body>"""


def _run_wait(browser, patrol, patience):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    # Nothing leaves the machine: the tracker host answers locally.
    ctx.route("https://track.adform.net/**", lambda r: r.fulfill(status=200, body=""))
    try:
        rec = session.Recorder()
        rec.attach(ctx)
        page = ctx.new_page()
        rec.bind(page)
        page.set_content(IN_VIEW_ONLY)
        meta = {"events": []}
        ok = strategies._wait_for_impression(
            rec, _settings(patience=patience, patrol=patrol, patrol_dwell=1),
            meta, wait_for=["7777777"], page=page)
        return ok, meta, page.evaluate("scrollY")
    finally:
        ctx.close()


def test_an_in_view_only_slot_fires_during_the_patrol(browser):
    ok, meta, y = _run_wait(browser, True, 12)
    assert ok is True, meta["events"]
    assert y > 0                                  # stayed where it fired


def test_parked_at_the_top_the_same_slot_never_fires(browser):
    """What the dziennik.pl runs did for 260s."""
    ok, _meta, _y = _run_wait(browser, False, 3)
    assert ok is False
