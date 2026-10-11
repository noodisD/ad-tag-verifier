"""backend/ is a flat package-less directory (app.py does `import engine`), so
put it on the path the same way running `python app.py` does.

Also the stand-in for worker processes the API tests run against: no browser,
no subprocess, and a behaviour picked per target id."""
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeProc:
    """One "worker": a thread doing what worker.py would do for this target,
    by the launcher's plan for its id.

    Plans: "ok" (default), "slow" (0.3s), "slow_start" (its browser comes up
    after 0.3s), "hang" (until its browser is killed), "crash" (exit 3, a
    traceback in worker.log), "fatal" (the browser could not start), "watch"
    (until its stop file appears), "watch_slow" (the same, then takes 0.5s to
    close), or a callable (job, proc) -> (exit code, result or None).
    """

    def __init__(self, launcher, job_path, log_path):
        self.launcher = launcher
        self.job_path, self.log_path = Path(job_path), Path(log_path)
        self.job = json.loads(self.job_path.read_text(encoding="utf-8"))
        self.tid = self.job["target"]["id"]
        self.code = None
        self.browser_killed = threading.Event()
        self.killed = threading.Event()
        self.closed = False
        self._done = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _launched(self):
        if self.job.get("launched_file"):
            Path(self.job["launched_file"]).touch()

    def _run(self):
        L = self.launcher
        with L.lock:
            L.live += 1
            L.peak = max(L.peak, L.live)
            L.started.append(self.tid)
            L.headless[self.tid] = self.job["headless"]
        try:
            plan = L.plan.get(self.tid, "ok")
            code, result = 0, {"status": "done"}
            if callable(plan):
                code, result = plan(self.job, self)
            elif plan == "slow":
                self._launched()
                time.sleep(0.3)
            elif plan == "hang":
                self._launched()
                while not (self.browser_killed.is_set() or self.killed.is_set()):
                    time.sleep(0.01)
                code, result = (1, None) if self.killed.is_set() else (0, {"status": "error", "detail": "Target closed"})
            elif plan == "crash":
                self.log_path.write_text("Traceback (most recent call last):\nRuntimeError: boom\n", encoding="utf-8")
                code, result = 3, None
            elif plan == "fatal":
                time.sleep(0.05)
                result = {"status": "error", "detail": "Executable doesn't exist at ...ms-playwright...",
                          "fatal": "launch"}
            elif plan in ("watch", "watch_slow"):
                self._launched()
                stop = Path(self.job["stop_file"])
                while not (stop.exists() or self.killed.is_set()):
                    time.sleep(0.01)
                if plan == "watch_slow":
                    time.sleep(0.5)               # the window takes a moment to close
                result = {"status": "done", "watched": True}
            elif plan == "slow_start":
                time.sleep(0.3)                   # a browser still starting up
                self._launched()
                time.sleep(0.05)
            else:
                self._launched()
                time.sleep(0.02)
            if result is not None and not self.killed.is_set():
                self.job_path.with_name("result.json").write_text(json.dumps(result), encoding="utf-8")
            self.code = code if not self.killed.is_set() else 1
        finally:
            with L.lock:
                L.live -= 1
            self._done.set()

    def wait(self, timeout):
        return self.code if self._done.wait(timeout) else None

    def kill_browser(self):
        self.launcher.browser_kills.append(self.tid)
        self.browser_killed.set()

    def kill(self):
        self.launcher.kills.append(self.tid)
        self.killed.set()

    def peak_mem_mb(self):
        return None

    def close(self):
        self.closed = True


class FakeLauncher:
    def __init__(self):
        self.lock = threading.Lock()
        self.plan = {}
        self.live = self.peak = 0
        self.started, self.headless = [], {}
        self.kills, self.browser_kills = [], []
        self.procs = []

    def __call__(self, job_path, log_path, temp_dir):
        p = FakeProc(self, job_path, log_path)
        self.procs.append(p)
        return p


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    """The API with fake workers, its artifacts in tmp, and its clocks short."""
    import app as api
    fake = FakeLauncher()
    monkeypatch.setattr(api, "_LAUNCH", fake)
    monkeypatch.setattr(api, "ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(api, "TARGET_TIMEOUT_S", 10)     # tests about the cut-off shorten it
    monkeypatch.setattr(api, "STARTUP_ALLOWANCE_S", 0)
    monkeypatch.setattr(api, "KILL_GRACE_S", 0.5)
    monkeypatch.setattr(api, "LAUNCH_STAGGER_S", 0)
    monkeypatch.setattr(api, "_low_memory", lambda: False)
    return fake


@pytest.fixture
def client(launcher):
    import app as api
    api.RUNS.clear()
    api.app.config["TESTING"] = True
    with api.app.test_client() as c:
        yield c
        # A run left going would start its workers under the next test's
        # launcher (it is looked up when each worker starts). End them here.
        for run_id, run in list(api.RUNS.items()):
            if not run["done"]:
                c.post(f"/cancel/{run_id}")
        deadline = time.time() + 15
        while any(not r["done"] for r in list(api.RUNS.values())) and time.time() < deadline:
            time.sleep(0.02)


def await_done(client, path, run_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{path}/{run_id}").get_json()
        if body["done"]:
            return body
        time.sleep(0.02)
    raise AssertionError("run never finished")


def await_that(cond, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = cond()
        if v:
            return v
        time.sleep(0.02)
    raise AssertionError("condition never held")
