"""One target in its worker process. No browser: Playwright and the capture
are stand-ins, the same ones test_engine.py uses.

What crosses the process boundary is the job file and the result file, so
that is what is pinned: the result comes back readable, the stop signal
still works as a path, and a browser that cannot start is told apart from a
page that failed.
"""
import json

import engine
import worker
from test_engine import _fake_capture_with


class _Browser:
    closed = False

    def close(self):
        self.closed = True


class _Playwright:
    """sync_playwright() stand-in. `fail` picks where it breaks."""
    def __init__(self, fail=None):
        self.fail, self.browser, self.exited = fail, _Browser(), False

    def __call__(self):
        return self

    def __enter__(self):
        if self.fail == "enter":
            raise RuntimeError("Executable doesn't exist at ...ms-playwright...")
        return self

    def __exit__(self, *a):
        self.exited = True
        return False

    @property
    def chromium(self):
        return self

    def launch(self, headless=True, args=None):
        if self.fail == "launch":
            raise RuntimeError("Browser closed. TargetClosedError")
        self.headless = headless
        return self.browser


def _job(tmp_path, **kw):
    job = {"kind": "discover", "run_dir": str(tmp_path), "headless": True, "strategy": "load",
           "target": {"id": "t0", "url": "https://example.test/a"}, "stop_file": None,
           "launched_file": str(tmp_path / "launched")}
    job.update(kw)
    return job


def test_a_job_runs_and_closes_its_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.session, "capture", _fake_capture_with(tmp_path, []))
    pw = _Playwright()
    r = worker.run_job(_job(tmp_path), playwright_factory=pw)
    assert r["status"] in ("done", "none")
    assert "fatal" not in r
    assert pw.browser.closed and pw.exited
    assert (tmp_path / "launched").exists(), "the parent learns a browser can start here"


def test_main_writes_a_readable_result_beside_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "run_job", lambda job: {"status": "error", "detail": "zażółć gęślą"})
    d = tmp_path / "t0"
    d.mkdir()
    (d / "job.json").write_text(json.dumps(_job(tmp_path)), encoding="utf-8")
    assert worker.main([str(d / "job.json")]) == 0
    assert json.loads((d / "result.json").read_text(encoding="utf-8"))["detail"] == "zażółć gęślą"


def test_the_stop_file_is_the_watch_signal(tmp_path, monkeypatch):
    """The parent cannot hand a threading.Event to another process; a file
    it can. The capture loop polls stop_check, so it must follow the file."""
    seen = {}
    fake = _fake_capture_with(tmp_path, [])

    def capture(job, browser, run_dir, viewport="desktop", overrides=None):
        seen.update(overrides or {})
        return fake(job, browser, run_dir, viewport, overrides)

    monkeypatch.setattr(engine.session, "capture", capture)
    stop = tmp_path / "watch.stop"
    worker.run_job(_job(tmp_path, stop_file=str(stop)), playwright_factory=_Playwright())
    assert seen["stop_check"]() is False
    stop.touch()
    assert seen["stop_check"]() is True
    assert seen["announce"] is False


def test_overrides_from_the_job_are_not_trusted(tmp_path, monkeypatch):
    seen = {}
    fake = _fake_capture_with(tmp_path, [])

    def capture(job, browser, run_dir, viewport="desktop", overrides=None):
        seen.update(overrides or {})
        return fake(job, browser, run_dir, viewport, overrides)

    monkeypatch.setattr(engine.session, "capture", capture)
    job = _job(tmp_path)
    job["target"]["overrides"] = {"announce": True, "patience": 9999}
    worker.run_job(job, playwright_factory=_Playwright())
    assert seen["announce"] is False and "patience" not in seen


def test_a_browser_that_cannot_start_is_marked_fatal(tmp_path):
    for where in ("enter", "launch"):
        r = worker.run_job(_job(tmp_path), playwright_factory=_Playwright(fail=where))
        assert r["status"] == "error" and r["fatal"] == "launch", where
        assert not (tmp_path / "launched").exists()


def test_a_page_that_fails_is_not_fatal(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("page crashed")
    monkeypatch.setattr(engine.session, "capture", boom)
    pw = _Playwright()
    r = worker.run_job(_job(tmp_path), playwright_factory=pw)
    assert r == {"status": "error", "detail": "page crashed"}
    assert pw.browser.closed
