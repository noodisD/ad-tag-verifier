"""Waiting that can see what arrives while it waits.

Recorder.wait_for used to poll with time.sleep(). Playwright's sync API hands
events to Python only while a call into it is running, so nothing fired during
the wait reached the recorder until the wait was over: on dziennik.pl the
Commercial Break's Adform impression fired at 13s (server clock) and was
recorded at 274s, and a wait could only ever end on a beacon that had arrived
before it began.
"""
import time
import types

import pytest

from core.analyze import vendors
from core.capture import consent, session, strategies


# ── offline: the pause itself ─────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


class _WaitingPage:
    def __init__(self, clock):
        self.clock, self.waits = clock, []

    def wait_for_timeout(self, ms):
        self.waits.append(ms)
        self.clock.now += ms / 1000


def test_a_pause_waits_on_the_page_in_short_slices(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(consent, "time", clock)
    page = _WaitingPage(clock)
    consent.pause(page, 1.2)
    assert page.waits and max(page.waits) <= 500
    assert abs(sum(page.waits) - 1200) < 1


def test_a_page_that_is_gone_is_a_plain_sleep(monkeypatch):
    """Watch mode: the person closes the window mid-wait."""
    clock = _Clock()
    monkeypatch.setattr(consent, "time", clock)

    class Closed:
        def wait_for_timeout(self, ms):
            raise RuntimeError("Target page, context or browser has been closed")

    consent.pause(Closed(), 2)                    # must not raise
    assert abs(clock.now - 1002.0) < 1e-6


def test_an_unbound_recorder_still_waits(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(consent, "time", clock)
    session.Recorder().sleep(1.5)
    assert abs(clock.now - 1001.5) < 1e-6


def test_the_wait_looks_once_more_at_its_deadline(monkeypatch):
    """A beacon delivered during the last poll is not thrown away."""
    clock = _Clock()
    monkeypatch.setattr(consent, "time", clock)
    monkeypatch.setattr(session, "time", clock)
    rec = session.Recorder()
    rec.bind(_WaitingPage(clock))
    start = clock.now
    assert rec.wait_for(lambda: clock.now - start >= 2.0, 2.0, poll=0.5) is True


def test_the_recorder_waits_on_the_page_it_is_bound_to(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(consent, "time", clock)
    monkeypatch.setattr(session, "time", clock)
    rec, page = session.Recorder(), _WaitingPage(clock)
    rec.bind(page)
    assert rec.wait_for(lambda: False, 1.0, poll=0.5) is False
    assert page.waits, "the wait must go through the page, not time.sleep"


# ── the frame a click aims at ─────────────────────────────────────────────

def test_impression_frame_takes_a_set_and_never_falls_back_to_a_stranger():
    """dziennik.pl: with nothing of the sheet's fired, the old lookup took the
    first impression of anyone — the pre-roll's CM360 frame — and clicked it."""
    rec = session.Recorder()
    rec.note("https://ad.doubleclick.net/ddm/trackimp/N1.2/B3.455988298;x", True, frame="A")
    rec.note("https://track.adform.net/adfserve/?bn=90571117;1x1inv=1", True, frame="B")
    assert rec.impression_frame({"90571117"}) == "B"
    assert rec.impression_frame(("90571117", "1")) == "B"
    assert rec.impression_frame({"1"}) is None
    assert rec.impression_frame("455988298") == "A"
    assert rec.impression_frame(None) == "A"         # no sheet: as before


# ── capture() binds the recorder ──────────────────────────────────────────

class _FakePage:
    frames = []
    url = "about:blank"

    def screenshot(self, path=None, **kw):
        pass

    def goto(self, *a, **k):
        pass


class _FakeCtx:
    def __init__(self):
        self.pages = []

    def on(self, *a):
        pass

    def new_page(self):
        p = _FakePage()
        self.pages.append(p)
        return p

    def close(self):
        pass


class _FakeBrowser:
    def new_context(self, **kw):
        return _FakeCtx()


def test_capture_binds_the_recorder_to_the_test_page(monkeypatch, tmp_path):
    seen = {}

    def drive(page, ctx, recorder, settings, meta, target):
        seen["bound"] = recorder.page is page

    monkeypatch.setattr(strategies, "get", lambda name: drive)
    session.capture({"id": "t0", "url": "https://pub.example/"}, _FakeBrowser(), tmp_path)
    assert seen["bound"] is True


# ── live: a real page, a beacon fired mid-wait ────────────────────────────

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


LATE_PIXEL = ("<script>setTimeout(() => { new Image().src = "
              "'https://track.adform.net/adfserve/?bn=12345678;1x1inv=1'; }, 2000);</script>")


def _ctx(browser):
    ctx = browser.new_context()
    # Nothing leaves the machine: the tracker host answers locally.
    ctx.route("https://track.adform.net/**", lambda r: r.fulfill(status=200, body=""))
    return ctx


def test_a_pumping_wait_sees_a_beacon_that_fires_during_it(browser):
    ctx = _ctx(browser)
    try:
        rec = session.Recorder()
        rec.attach(ctx)
        page = ctx.new_page()
        rec.bind(page)
        page.set_content(LATE_PIXEL)
        t = time.time()
        ok = rec.wait_for(lambda: rec.has(kind=vendors.IMPRESSION, ident="12345678"), 10)
        took = time.time() - t
        assert ok is True
        assert took < 5, f"seen only after {took:.1f}s"
        b = next(b for b in rec.beacons if b["id"] == "12345678")
        # Stamped when it fired (~2s), not when some later call caught up.
        assert 1.5 <= b["t"] <= 4.0, b["t"]
    finally:
        ctx.close()


def test_a_sleeping_wait_was_blind(browser):
    """Pins the cause: the same wait over time.sleep never sees it."""
    ctx = _ctx(browser)
    try:
        rec = session.Recorder()
        rec.attach(ctx)
        page = ctx.new_page()
        rec.sleep = time.sleep                   # the old, unbound behaviour
        page.set_content(LATE_PIXEL)
        assert rec.wait_for(lambda: rec.has(kind=vendors.IMPRESSION, ident="12345678"),
                            3.5) is False
    finally:
        ctx.close()


def test_consent_settling_lets_beacons_through(browser):
    """consent.accept's settle used to be a time.sleep too."""
    ctx = _ctx(browser)
    try:
        rec = session.Recorder()
        rec.attach(ctx)
        page = ctx.new_page()
        page.set_content(LATE_PIXEL)
        t = time.time()
        consent.pause(page, 3)
        assert any(b["id"] == "12345678" for b in rec.beacons)
        b = next(b for b in rec.beacons if b["id"] == "12345678")
        assert b["t"] < (time.time() - rec.t0) - 0.3, "stamped at the end of the pause"
        assert time.time() - t >= 2.9
    finally:
        ctx.close()
