"""Running targets in parallel. No browser: workers are conftest's stand-ins,
plus two real processes at the end to pin what the Job Object promises.

What is pinned is what parallel runs could quietly get wrong: more browsers
than asked for, one stuck page taking its neighbours down, a dead run that
looks finished, and a watch window the operator cannot end.
"""
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

import app as api
from conftest import await_done, await_that

LOAD = "https://example.test/page-{}"
WATCH_URL = "https://preview.adnami.io/creative/abc"     # profiles.yaml -> watch


def _targets(n, prefix="t"):
    return [{"id": f"{prefix}{i}", "url": LOAD.format(f"{prefix}{i}")} for i in range(n)]


def _scan(client, targets, **opts):
    r = client.post("/discover", json={"targets": targets, **opts})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_never_more_than_the_requested_concurrency(client, launcher):
    launcher.plan = {f"t{i}": "slow" for i in range(8)}
    run = _scan(client, _targets(8), concurrency=3)
    assert run["concurrency"] == 3
    body = await_done(client, "/discover", run["run_id"])
    assert all(r["status"] == "done" for r in body["results"].values())
    assert launcher.peak == 3


def test_the_cap_holds_across_overlapping_runs(client, launcher, monkeypatch):
    """A verify and a scan at once share one budget of browsers."""
    monkeypatch.setattr(api, "_SLOTS", threading.BoundedSemaphore(2))
    launcher.plan = {t["id"]: "slow" for t in _targets(3, "a") + _targets(3, "b")}
    one = _scan(client, _targets(3, "a"), concurrency=2)
    two = _scan(client, _targets(3, "b"), concurrency=2)
    await_done(client, "/discover", one["run_id"])
    await_done(client, "/discover", two["run_id"])
    assert launcher.peak <= 2


def test_a_stuck_page_is_cut_off_alone(client, launcher, monkeypatch):
    """kultura.onet.pl sat for 22 minutes and held every test behind it. The
    old guard killed every browser the server owned; with ten running, that
    takes nine healthy pages down with the stuck one."""
    monkeypatch.setattr(api, "TARGET_TIMEOUT_S", 0.5)
    launcher.plan = {"t0": "hang", "t1": "slow", "t2": "slow"}
    run = _scan(client, _targets(3), concurrency=3)
    body = await_done(client, "/discover", run["run_id"])
    res = body["results"]
    assert res["t0"]["status"] == "error" and "stopped responding" in res["t0"]["detail"]
    assert res["t1"]["status"] == "done" and res["t2"]["status"] == "done"
    assert launcher.browser_kills == ["t0"]
    assert "t1" not in launcher.kills and "t2" not in launcher.kills


def test_a_crashed_worker_says_so(client, launcher):
    launcher.plan = {"t0": "crash"}
    body = await_done(client, "/discover", _scan(client, _targets(1))["run_id"])
    detail = body["results"]["t0"]["detail"]
    assert "worker crashed (exit code 3)" in detail and "boom" in detail


def test_a_browser_that_cannot_start_stops_the_run(client, launcher):
    """Chromium not installed: every target would fail the same way. Say it
    once, on the run, and do not start the rest."""
    launcher.plan = {f"t{i}": "fatal" for i in range(5)}
    body = await_done(client, "/discover", _scan(client, _targets(5), concurrency=1)["run_id"])
    assert body["error"] and "Executable doesn't exist" in body["error"]
    assert all(r["status"] == "error" for r in body["results"].values())
    assert launcher.started == ["t0"]
    assert "fatal" not in body["results"]["t0"], "an internal marker, not part of the result"


def test_one_failed_start_beside_working_browsers_is_that_targets_problem(client, launcher):
    """Out of memory for one Chromium among ten is not "chromium is missing"."""
    launcher.plan = {"t0": "fatal", "t1": "slow", "t2": "slow", "t3": "slow"}
    body = await_done(client, "/discover", _scan(client, _targets(4), concurrency=3)["run_id"])
    assert body["error"] is None
    assert body["results"]["t0"]["status"] == "error"
    assert [body["results"][t]["status"] for t in ("t1", "t2", "t3")] == ["done"] * 3


def test_a_failed_start_beside_browsers_still_starting_is_not_fatal(client, launcher):
    """One target's browser failed while its sibling's was still coming up: the
    run was declared dead and the queue stopped, with the sibling about to
    prove the browser works. The decision waits for the siblings."""
    launcher.plan = {"t0": "fatal", "t1": "slow_start"}
    body = await_done(client, "/discover", _scan(client, _targets(4), concurrency=2)["run_id"])
    assert body["error"] is None
    assert body["results"]["t0"]["status"] == "error"
    assert [body["results"][t]["status"] for t in ("t1", "t2", "t3")] == ["done"] * 3


def test_a_window_that_cannot_open_does_not_fail_the_headless_pool(client, launcher):
    launcher.plan = {"w0": "fatal"}
    targets = [{"id": "w0", "url": WATCH_URL}] + _targets(3)
    body = await_done(client, "/discover", _scan(client, targets, concurrency=3)["run_id"])
    assert body["error"] is None
    assert body["results"]["w0"]["status"] == "error"
    assert [body["results"][f"t{i}"]["status"] for i in range(3)] == ["done"] * 3


def test_a_wide_pool_that_cannot_start_browsers_stops_after_the_first_wave(client, launcher):
    """Chromium missing, twelve targets, four slots: one wave of failures, then
    the run says why. It must not go on to start the other eight."""
    launcher.plan = {f"t{i}": "fatal" for i in range(12)}
    body = await_done(client, "/discover", _scan(client, _targets(12), concurrency=4)["run_id"])
    assert body["error"] and "Executable doesn't exist" in body["error"]
    assert len(launcher.started) == 4
    assert all(r["status"] == "error" for r in body["results"].values())


def test_a_cancel_during_the_launch_stagger_stops_the_workers_still_queued(client, launcher, monkeypatch):
    """Each slot had passed its checks and was waiting its turn to launch; a
    cancel in that window killed only the workers already registered, and the
    rest started afterwards — each a real Chromium nobody could stop."""
    monkeypatch.setattr(api, "LAUNCH_STAGGER_S", 0.2)
    launcher.plan = {f"t{i}": "hang" for i in range(10)}
    run_id = _scan(client, _targets(10), concurrency=10)["run_id"]
    await_that(lambda: len(launcher.started) >= 2)
    assert client.post(f"/cancel/{run_id}").status_code == 200
    body = await_done(client, "/discover", run_id)
    launched = len(launcher.started)
    time.sleep(0.6)
    assert len(launcher.started) == launched, "nothing may start after a cancel"
    assert launched < 10
    assert sorted(launcher.kills) == sorted(launcher.started), "every worker that did start was ended"
    assert all(r["status"] == "error" for r in body["results"].values())
    assert not any(r["status"] == "running" for r in api.RUNS[run_id]["results"].values())


def test_a_slot_that_frees_up_just_after_a_cancel_does_not_start_the_next_target():
    import threading
    slots = threading.BoundedSemaphore(1)
    api._SLOTS, saved = slots, api._SLOTS
    try:
        api.RUNS.clear()
        run_id = api._create_run("discover", [{"id": "a"}], [])
        slots.acquire()                               # someone else holds the only slot
        out = {}
        th = threading.Thread(target=lambda: out.update(ok=api._await_capacity(run_id)))
        th.start()
        time.sleep(0.2)
        api.RUNS[run_id]["cancelled"] = True
        slots.release()                               # it frees up just after the cancel
        th.join(5)
        assert out["ok"] is False
        assert slots.acquire(blocking=False), "a cancelled run must not be left holding the slot"
    finally:
        api._SLOTS = saved
        api.RUNS.clear()


def test_low_memory_holds_back_the_first_wave(client, launcher, monkeypatch):
    """The guard counted workers already running, and in the first wave none
    were yet: every slot read "none" and all of them started together."""
    monkeypatch.setattr(api, "_low_memory", lambda: api._workers_running() >= 2)
    launcher.plan = {f"t{i}": "slow" for i in range(6)}
    body = await_done(client, "/discover", _scan(client, _targets(6), concurrency=6)["run_id"])
    assert all(r["status"] == "done" for r in body["results"].values())
    assert launcher.peak == 2


def test_low_memory_does_not_stall_the_run_for_good(client, launcher, monkeypatch):
    """Memory that stays low with nothing of ours running would wait forever."""
    monkeypatch.setattr(api, "_low_memory", lambda: True)
    launcher.plan = {f"t{i}": "slow" for i in range(4)}
    body = await_done(client, "/discover", _scan(client, _targets(4), concurrency=4)["run_id"], timeout=15)
    assert all(r["status"] == "done" for r in body["results"].values())
    assert launcher.peak == 1


def test_a_cancel_while_waiting_for_memory_starts_nothing_more(client, launcher, monkeypatch):
    monkeypatch.setattr(api, "_low_memory", lambda: True)
    launcher.plan = {f"t{i}": "hang" for i in range(4)}
    run_id = _scan(client, _targets(4), concurrency=4)["run_id"]
    await_that(lambda: len(launcher.started) == 1)
    time.sleep(0.3)
    client.post(f"/cancel/{run_id}")
    body = await_done(client, "/discover", run_id)
    assert launcher.started == [launcher.started[0]], "the others were waiting for memory, not started"
    assert all(r["status"] == "error" for r in body["results"].values())


def test_an_error_preparing_one_target_does_not_end_its_slot(client, launcher, monkeypatch):
    """Anything raised before a worker was launched ended the slot's thread. In
    a lane of width one that was every target after it, reported "never ran"."""
    real = api._run_target

    def flaky(run_id, kind, run_dir, item, headless):
        if item["target"]["id"] == "t0":
            raise OSError("disk full")
        return real(run_id, kind, run_dir, item, headless)

    monkeypatch.setattr(api, "_run_target", flaky)
    body = await_done(client, "/discover", _scan(client, _targets(3), concurrency=1)["run_id"])
    assert body["results"]["t0"]["status"] == "error" and "disk full" in body["results"]["t0"]["detail"]
    assert body["results"]["t1"]["status"] == "done" and body["results"]["t2"]["status"] == "done"


def test_after_done_the_snapshot_stops_naming_the_watch(client, launcher):
    """The window takes a moment to close, and for that moment the page read
    "waiting for you" again; a second click was refused with a 409 that then
    stayed up as an error for the rest of the run."""
    launcher.plan = {"w0": "watch_slow"}
    run_id = _scan(client, [{"id": "w0", "url": WATCH_URL}])["run_id"]
    await_that(lambda: client.get(f"/discover/{run_id}").get_json()["watch_active"] == "w0")
    assert client.post(f"/watch/{run_id}/done", json={"id": "w0"}).status_code == 200
    snap = client.get(f"/discover/{run_id}").get_json()
    assert snap["watch_active"] is None
    assert snap["results"]["w0"]["status"] == "running", "still closing"
    assert client.post(f"/watch/{run_id}/done", json={"id": "w0"}).status_code == 200
    assert await_done(client, "/discover", run_id)["results"]["w0"]["watched"] is True


def test_watch_rows_run_beside_the_pool_one_at_a_time_headed(client, launcher):
    launcher.plan = {"w0": "watch", "w1": "watch"}
    targets = [{"id": "w0", "url": WATCH_URL}, {"id": "w1", "url": WATCH_URL + "?2"}] + _targets(3)
    run_id = _scan(client, targets, concurrency=3)["run_id"]

    snap = lambda: client.get(f"/discover/{run_id}").get_json()
    await_that(lambda: snap()["watch_active"] == "w0")
    # The pool does not wait for the person.
    await_that(lambda: all(snap()["results"][f"t{i}"]["status"] == "done" for i in range(3)))
    assert snap()["results"]["w1"]["status"] == "pending"

    assert client.post(f"/watch/{run_id}/done", json={"id": "w0"}).status_code == 200
    await_that(lambda: snap()["watch_active"] == "w1")
    # The old signal was one flag for the run, never cleared: the second
    # watch target ended the moment it began.
    time.sleep(0.3)
    assert snap()["results"]["w1"]["status"] == "running"

    assert client.post(f"/watch/{run_id}/done", json={"id": "w1"}).status_code == 200
    body = await_done(client, "/discover", run_id)
    assert body["results"]["w0"]["watched"] and body["results"]["w1"]["watched"]
    assert launcher.headless == {"w0": False, "w1": False, "t0": True, "t1": True, "t2": True}


def test_ending_a_watch_that_is_not_the_open_one_is_refused(client, launcher):
    launcher.plan = {"w0": "watch", "w1": "watch"}
    run_id = _scan(client, [{"id": "w0", "url": WATCH_URL}, {"id": "w1", "url": WATCH_URL + "?2"}])["run_id"]
    await_that(lambda: client.get(f"/discover/{run_id}").get_json()["watch_active"] == "w0")
    r = client.post(f"/watch/{run_id}/done", json={"id": "w1"})
    assert r.status_code == 409 and r.get_json()["watch_active"] == "w0"
    client.post(f"/cancel/{run_id}")
    await_done(client, "/discover", run_id)


def test_show_browser_means_one_at_a_time_in_order(client, launcher):
    """Chrome throttles windows it thinks are hidden: several at once and
    every one but the front one runs slow."""
    run = _scan(client, _targets(4), concurrency=10, headed=True)
    assert run["concurrency"] == 1
    await_done(client, "/discover", run["run_id"])
    assert launcher.started == ["t0", "t1", "t2", "t3"]
    assert launcher.peak == 1
    assert set(launcher.headless.values()) == {False}


def test_the_longest_wait_starts_first(client, launcher):
    """The run ends when its slowest target does; it should not start last."""
    targets = _targets(2) + [{"id": "slowest", "url": "https://www.dziennik.pl/?version=x"}]
    await_done(client, "/discover", _scan(client, targets, concurrency=1)["run_id"])
    assert launcher.started[0] == "slowest"


def test_a_running_row_says_for_how_long(client, launcher):
    launcher.plan = {"t0": "hang"}
    run_id = _scan(client, _targets(1))["run_id"]
    row = await_that(lambda: (r := client.get(f"/discover/{run_id}").get_json()["results"]["t0"])
                     .get("status") == "running" and r)
    assert isinstance(row["elapsed_s"], int)
    assert "elapsed_s" not in api.RUNS[run_id]["results"]["t0"], "the stored row is left as it was"
    client.post(f"/cancel/{run_id}")
    await_done(client, "/discover", run_id)


def test_concurrency_is_clamped(client, launcher):
    assert _scan(client, _targets(1, "a"), concurrency=99)["concurrency"] == api.MAX_PARALLEL
    assert _scan(client, _targets(1, "b"), concurrency=0)["concurrency"] == 1
    assert _scan(client, _targets(1, "c"), concurrency="lots")["concurrency"] == api.DEFAULT_CONCURRENCY


def test_cancel_stops_the_queue_and_closes_the_browsers(client, launcher):
    launcher.plan = {f"t{i}": "hang" for i in range(6)}
    run_id = _scan(client, _targets(6), concurrency=2)["run_id"]
    await_that(lambda: len(launcher.started) == 2)
    assert client.post(f"/cancel/{run_id}").status_code == 200
    body = await_done(client, "/discover", run_id)
    assert all(r["status"] == "error" for r in body["results"].values())
    assert sorted(launcher.kills) == sorted(launcher.started)
    assert len(launcher.started) == 2, "nothing queued may start after a cancel"


def test_a_run_in_flight_is_never_pruned():
    """Its slots would keep starting browsers for a run nobody could see."""
    api.RUNS.clear()
    for i in range(api.MAX_RUNS + 3):
        api.RUNS[f"old{i}"] = {"done": True, "finished": time.time(), "created": i}
    api.RUNS["live"] = {"done": False, "finished": None, "created": -1}
    with api._LOCK:
        api._prune_locked()
    assert "live" in api.RUNS
    assert len(api.RUNS) == api.MAX_RUNS
    api.RUNS.clear()


# ── real processes: what the Job Object promises ─────────────────────────

_PARENT = textwrap.dedent("""
    import subprocess, sys, time
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    open(sys.argv[1], "w").write(str(child.pid))
    time.sleep(120)
""")


def _start_tree(tmp_path, monkeypatch):
    import procs
    pid_file = tmp_path / "grandchild.pid"
    script = tmp_path / "parent.py"
    script.write_text(_PARENT, encoding="utf-8")
    monkeypatch.setattr(procs, "worker_command", lambda job: [sys.executable, str(script), str(pid_file)])
    w = procs.launch(tmp_path / "job.json", tmp_path / "worker.log", tmp_path / "tmp")
    grandchild = int(await_that(lambda: pid_file.exists() and pid_file.read_text().strip() or None, timeout=20))
    return w, grandchild


def _gone(pid):
    psutil = pytest.importorskip("psutil")
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows")
def test_killing_a_worker_takes_its_whole_tree(tmp_path, monkeypatch):
    """In the real thing the grandchild is Chromium, under the Playwright driver."""
    w, grandchild = _start_tree(tmp_path, monkeypatch)
    w.kill()
    assert w.wait(10) is not None
    await_that(lambda: _gone(grandchild), timeout=10)
    w.close()


_HOLDER = textwrap.dedent("""
    import subprocess, sys, time
    # The grandchild keeps a file open in the worker's TEMP, as Chromium does
    # with its profile; Windows will not delete a folder with a file open in it.
    code = ("import os, time; "
            "f = open(os.path.join(os.environ['TEMP'], 'held.bin'), 'wb'); time.sleep(120)")
    child = subprocess.Popen([sys.executable, "-c", code])
    open(sys.argv[1], "w").write(str(child.pid))
    time.sleep(120)
""")


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows")
def test_a_killed_workers_temp_folder_is_deleted_after_its_browser_lets_go(tmp_path, monkeypatch):
    """The folder was deleted the instant the worker was killed, while its
    Chromium still held a file in it — so it was left behind, and nothing
    ever came back for it."""
    import procs
    pid_file = tmp_path / "grandchild.pid"
    script = tmp_path / "holder.py"
    script.write_text(_HOLDER, encoding="utf-8")
    monkeypatch.setattr(procs, "worker_command", lambda job: [sys.executable, str(script), str(pid_file)])
    temp = tmp_path / "worker-temp"
    w = procs.launch(tmp_path / "job.json", tmp_path / "worker.log", temp)
    await_that(lambda: pid_file.exists() and pid_file.read_text().strip() and (temp / "held.bin").exists(),
               timeout=20)
    w.kill()
    assert w.wait(10) is not None
    w.close()
    assert not temp.exists(), "close() returned with the worker's temp folder still on disk"


def test_a_relative_credentials_path_reaches_the_worker_as_an_absolute_one(tmp_path, monkeypatch):
    """Workers start in the repo, not where the API was started: a relative
    path pointed somewhere else, and the vision fallback quietly turned itself
    off when its credentials file was not found."""
    import os
    import procs
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "creds.json")
    monkeypatch.setattr(procs, "worker_command", lambda job: [
        sys.executable, "-c", "import os; print(os.environ['GOOGLE_APPLICATION_CREDENTIALS'])"])
    w = procs.launch(tmp_path / "job.json", tmp_path / "worker.log", tmp_path / "tmp")
    assert w.wait(30) == 0
    w.close()
    seen = (tmp_path / "worker.log").read_text(encoding="utf-8").strip()
    assert os.path.isabs(seen)
    assert os.path.normcase(os.path.realpath(seen)) == os.path.normcase(os.path.realpath(tmp_path / "creds.json"))


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows")
def test_closing_the_job_ends_whatever_is_left(tmp_path, monkeypatch):
    """What happens to every browser when the API itself goes away."""
    w, grandchild = _start_tree(tmp_path, monkeypatch)
    w.close()
    await_that(lambda: _gone(grandchild) and _gone(w.pid), timeout=10)
    assert not (tmp_path / "tmp").exists(), "the worker's temp folder goes with it"
