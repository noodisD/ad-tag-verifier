"""
Flask API for the Tag ID Extractor frontend's "Verify" step.

POST /verify   { targets: [{id, platform, url, expected}, ...],
                 concurrency?: 1-20, headed?: bool }
                                -> { run_id, rejected: [{id, reason}], concurrency }
GET  /verify/<run_id>           -> { done, error, results: { <id>: {status, ...} } }
POST /discover { targets: [{id, url}, ...], concurrency?, headed? }
                                -> { run_id, rejected: [{id, reason}], concurrency }
GET  /discover/<run_id>         -> { done, error, results, watch_active }
POST /watch/<run_id>/done       { id? } -> ends the watch target running now
POST /cancel/<run_id>           -> stops the run and every browser it started
GET  /health                    -> { ok: true }

The run happens on a background thread after the POST response returns —
same reasoning as UXAgent: the HTTP request that kicks off a run shouldn't
block on however long a batch of live page loads takes. Run state is held
in memory (RUNS), so this is a single-process, single-worker service.

Targets run in parallel, `concurrency` at a time (default 10), each in a
process of its own (worker.py) with its own browser. procs.py says why
processes and not threads.

Two properties matter to the caller and are easy to get wrong:

- **A run that dies still reports.** If the browser cannot start at all — by
  far the most common cause being that `playwright install chromium` was never
  run — every row would otherwise stay "pending" while `done` flips to true,
  which reads as a clean finish that found nothing.
- **A run_id belongs to one endpoint.** /verify and /discover return different
  result shapes, so looking one up on the other's endpoint is a 404, not a
  200 carrying a shape the caller cannot read.
"""

import collections
import json
import os
import re
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request

# backend/ is run as a flat directory (`python app.py`), so put the repo root
# on the path before importing core/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine                                    # noqa: E402,F401  (workers import it too)
import procs                                     # noqa: E402
from core.ai import match as ai_match           # noqa: E402
from core import profiles as core_profiles       # noqa: E402
from core.capture import session as core_session  # noqa: E402
from core.capture import strategies as core_strategies  # noqa: E402

app = Flask(__name__)

# Run state. Mutated from worker threads and read from request threads, so
# every access goes through _LOCK — reads hand back a copy, because jsonify
# serializing a dict a worker is still writing to is a RuntimeError waiting
# for the first person to add a key.
_LOCK = threading.Lock()
RUNS = {}
MAX_RUNS = 20        # nothing here is durable; cap it so a long session cannot grow forever
RUN_TTL_S = 3600

# Outside the repo by default — see core_session.default_artifact_root. Absolute
# either way: the old relative default resolved against backend/ and put HARs
# of live campaign pages in a path .gitignore did not cover.
ARTIFACT_ROOT = core_session.default_artifact_root()


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


# ── run bookkeeping ──────────────────────────────────────────────────────

def _prune_locked():
    """Drop expired runs, then cap. Caller holds _LOCK.

    A run still in flight is never dropped: its slots would carry on
    starting browsers for a run nobody can see or cancel any more."""
    now = time.time()
    for key in [k for k, r in RUNS.items()
                if r["done"] and now - r["finished"] > RUN_TTL_S]:
        del RUNS[key]
    if len(RUNS) > MAX_RUNS:
        finished = sorted((k for k in RUNS if RUNS[k]["done"]), key=lambda k: RUNS[k]["created"])
        for key in finished[:len(RUNS) - MAX_RUNS]:
            del RUNS[key]


# Ids become folder names under the run directory: "../x" must not leave it,
# and Windows will not tell "G1" from "g1", "G1." from "G1", or make a folder
# called NUL (writing NUL\job.json raises, and that used to end the slot).
_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)


def _split_targets(raw, need_platform):
    """-> (accepted, rejected). Rejected targets are reported rather than
    dropped: silently ignoring one leaves its row pending in the UI forever
    with nothing to explain why."""
    accepted, rejected = [], []
    if not isinstance(raw, list):
        return [], [{"id": None, "reason": "targets must be a list"}]

    seen = set()
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            rejected.append({"id": None, "reason": f"target #{i} is not an object"})
            continue
        missing = [k for k in ("id", "url") if not t.get(k)]
        if need_platform and not t.get("platform"):
            missing.append("platform")
        if missing:
            rejected.append({"id": t.get("id"), "reason": "missing " + ", ".join(missing)})
            continue
        tid = str(t["id"])
        if not _ID_OK.match(tid):
            rejected.append({"id": tid, "reason": "id may only use letters, digits, '.', '_' and '-'"})
        elif _RESERVED.match(tid) or tid.endswith("."):
            rejected.append({"id": tid, "reason": "id is a reserved Windows name, or ends with a dot"})
        elif tid.lower() in seen:
            rejected.append({"id": tid, "reason": "duplicate id"})
        else:
            seen.add(tid.lower())
            accepted.append(dict(t, id=tid))
    return accepted, rejected


def _profile_for(target):
    """-> (strategy, patience) as profiles.yaml says this URL should be
    driven. Resolved here rather than in the worker so the launch mode is
    known before any browser starts."""
    try:
        s = core_profiles.resolve(target["url"], viewport=target.get("viewport", "desktop"))
        return s["strategy"], s.get("patience") or 0
    except Exception:
        return "load", 0


def _strategy_for(target):
    return _profile_for(target)[0]


def _create_run(kind, accepted, rejected, **extra):
    run_id = uuid.uuid4().hex[:12]
    results = {t["id"]: {"status": "pending"} for t in accepted}
    for r in rejected:
        # A duplicate is rejected under the same id as the row that was
        # accepted; reporting it must not overwrite that row's own state.
        if r["id"] and r["id"] not in results:
            results[r["id"]] = {"status": "error", "detail": r["reason"]}
    with _LOCK:
        _prune_locked()
        RUNS[run_id] = {"kind": kind, "created": time.time(), "finished": None,
                        "done": False, "error": None, "results": results,
                        "procs": {}, "cancelled": False, "fatal": None, "launched_ok": 0,
                        # Targets between being taken off the queue and finishing —
                        # the siblings that might still show a browser can start.
                        "launching": 0,
                        # Why the last browser start failed, until another proves
                        # the browser works here (or none is left that could).
                        "suspect": None,
                        # tid -> the file a worker creates once its browser is up.
                        "markers": {},
                        "watch_ids": [], "watch_active": None, "watch_stop": {},
                        "watch_ended": set(),
                        **extra}
    return run_id


def _set_result(run_id, target_id, result):
    with _LOCK:
        run = RUNS.get(run_id)
        if run:
            run["results"][target_id] = result


def _fail_run(run_id, detail):
    """The run itself died. Say so, and stop any row still claiming to be
    on its way."""
    with _LOCK:
        run = RUNS.get(run_id)
        if not run:
            return
        run["error"] = detail
        for tid, r in run["results"].items():
            if r.get("status") in ("pending", "running"):
                run["results"][tid] = {"status": "error", "detail": detail}


def _finish_run(run_id):
    with _LOCK:
        run = RUNS.get(run_id)
        if run:
            run["done"] = True
            run["finished"] = time.time()


def _read_run(kind, run_id):
    """A snapshot, or None if this id is unknown *to this endpoint*."""
    with _LOCK:
        run = RUNS.get(run_id)
        if not run or run["kind"] != kind:
            return None
        now = time.time()
        results = {}
        for tid, r in run["results"].items():
            r = dict(r)                  # the stored row is left as it is
            if r.get("status") == "running" and r.get("started"):
                r["elapsed_s"] = int(now - r["started"])
            results[tid] = r
        # procs, stop files and the like stay put — they are not
        # serialisable, and the caller only needs to know which rows are
        # waiting on a person, and which of them is waiting now. A watch the
        # operator has ended is no longer waiting on them, though its window
        # takes a moment to close.
        active = run.get("watch_active")
        if active in run["watch_ended"]:
            active = None
        return {"done": run["done"], "error": run["error"],
                "artifacts": run.get("artifacts"),
                "watch_ids": run.get("watch_ids", []),
                "watch_active": active,
                "concurrency": run.get("concurrency"),
                "results": results}


# ── running targets ──────────────────────────────────────────────────────

# The longest one target may take. Every Playwright call on a page that stops
# answering waits forever — kultura.onet.pl sat for 22 minutes in a background
# run and held every test queued behind it. The slowest legitimate run is the
# video strategy (~200s), so this is generous.
TARGET_TIMEOUT_S = 420
# The clock starts when the worker process does, and a process has to import
# Playwright and start a browser before the old clock would have begun.
STARTUP_ALLOWANCE_S = 30
# After the browser is killed, the worker gets this long to write meta.json.
KILL_GRACE_S = 20
# Twenty cold starts of Python, Node and Chromium in the same instant is a
# stampede; spaced out they cost nothing anyone notices.
LAUNCH_STAGGER_S = 0.3

MAX_PARALLEL = 20


def _concurrency(raw, default=None):
    """1..MAX_PARALLEL; anything unusable falls back to the default."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CONCURRENCY if default is None else default
    return max(1, min(n, MAX_PARALLEL))


DEFAULT_CONCURRENCY = _concurrency(os.environ.get("TAGVERIFIER_CONCURRENCY"), default=10)
# A worker parsing a portal's HAR peaks at several times the file's size, on
# top of its browser. Below this, new targets wait for running ones to finish.
MIN_FREE_RAM_GB = 6

# Every browser this process starts, across overlapping runs.
_SLOTS = threading.BoundedSemaphore(MAX_PARALLEL)
_STAGGER = threading.Lock()

# Seams for the tests: how a worker is started, and how a run is put in the
# background. Patched there instead of threading.Thread or Playwright.
_LAUNCH = procs.launch


def _background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _run_alive(run_id):
    with _LOCK:
        run = RUNS.get(run_id)
        return bool(run) and not run["cancelled"] and not run["fatal"]


def _low_memory():
    try:
        import psutil
        return psutil.virtual_memory().available < MIN_FREE_RAM_GB * 2**30
    except Exception:
        return False


def _workers_running():
    with _LOCK:
        return sum(len(r["procs"]) for r in RUNS.values())


def _await_capacity(run_id):
    """Take a global slot. -> False if the run was cancelled meanwhile (no
    slot is held then). Checked again once the slot is in hand: a slot that
    frees up just after a cancel must not start the run's next target."""
    while not _SLOTS.acquire(timeout=1):
        if not _run_alive(run_id):
            return False
    if not _run_alive(run_id):
        _SLOTS.release()
        return False
    return True


def _wait_for_memory(run_id):
    """Hold the launch until there is memory for another browser. -> False if
    the run was cancelled meanwhile.

    Called under _STAGGER, just before each launch, so every launch sees the
    workers the launches before it started. Checked per slot ahead of that,
    the first wave all read "none running" and started together, which is
    exactly when the guard is needed. Waiting only makes sense while a worker
    of ours is using the memory; with none running it would never end."""
    while _low_memory() and _workers_running():
        if not _run_alive(run_id):
            return False
        time.sleep(0.5)
    return _run_alive(run_id)


def _read_result(path):
    try:
        r = json.loads(Path(path).read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else None
    except Exception:
        return None


def _last_line(path):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return lines[-1][:200] if lines else ""
    except Exception:
        return ""


def _run_target(run_id, kind, run_dir, item, headless):
    """One target in one worker process. -> its result, also recorded."""
    target, strategy = item["target"], item["strategy"]
    tid = target["id"]
    tdir = Path(run_dir) / tid
    tdir.mkdir(parents=True, exist_ok=True)
    watch = strategy == "watch"
    job = {"kind": kind,
           "target": {k: v for k, v in target.items() if k != "overrides"},
           "run_dir": str(run_dir), "headless": headless, "strategy": strategy,
           "stop_file": str(tdir / "watch.stop") if watch else None,
           "launched_file": str(tdir / "launched")}
    job_path = tdir / "job.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    (tdir / "result.json").unlink(missing_ok=True)

    with _STAGGER:
        # Everything queued here for the stagger has already passed the
        # checks in _slot: a cancel that came in meanwhile has to be seen
        # again, or each of them starts a browser nobody can stop.
        if not _wait_for_memory(run_id):
            result = {"status": "error", "detail": "cancelled before it ran"}
            _set_result(run_id, tid, result)
            return result
        try:
            proc = _LAUNCH(job_path, tdir / "worker.log",
                           Path(tempfile.gettempdir()) / f"{procs.TEMP_PREFIX}{run_id}-{tid}")
        except Exception as e:
            result = {"status": "error", "detail": f"could not start the worker: {e}"[:300]}
            _set_result(run_id, tid, result)
            return result
        with _LOCK:
            run = RUNS.get(run_id)
            # A cancel sweeps the workers registered at that moment. This one
            # was not yet, so it has to end itself.
            stale = not run or run["cancelled"]
            if run:
                run["procs"][tid] = proc
                run["markers"][tid] = job["launched_file"]
                if not stale:
                    run["results"][tid] = {"status": "running", "started": time.time()}
                    if watch:
                        run["watch_active"] = tid
        if stale:
            proc.kill()
        time.sleep(LAUNCH_STAGGER_S)

    code = proc.wait(TARGET_TIMEOUT_S + STARTUP_ALLOWANCE_S)
    timed_out = code is None
    if timed_out:
        proc.kill_browser()
        if proc.wait(KILL_GRACE_S) is None:
            proc.kill()
            proc.wait(10)

    with _LOCK:
        run = RUNS.get(run_id)
        cancelled = not run or run["cancelled"]
    result = _read_result(tdir / "result.json")
    if timed_out:
        result = {"status": "error",
                  "detail": f"the page stopped responding for {TARGET_TIMEOUT_S}s "
                            "and the browser was closed"}
    elif result is None:
        result = ({"status": "error", "detail": "cancelled"} if cancelled else
                  {"status": "error",
                   "detail": f"worker crashed (exit code {code})"
                             + (f": {_last_line(tdir / 'worker.log')}" if _last_line(tdir / "worker.log") else "")})
    fatal = result.pop("fatal", None)
    mem = proc.peak_mem_mb()
    if mem:
        result["worker_mem_mb"] = mem
    proc.close()

    with _LOCK:
        run = RUNS.get(run_id)
        if run:
            run["procs"].pop(tid, None)
            run["markers"].pop(tid, None)
            if run.get("watch_active") == tid:
                run["watch_active"] = None
            if fatal:
                # One failed start proves nothing yet: it may be this machine
                # short of memory, or a window it cannot open. _slot decides
                # once the siblings still starting have had their say.
                run["suspect"] = run["suspect"] or result.get("detail") or "the browser could not start"
            else:
                run["launched_ok"] += 1
            run["results"][tid] = result
    return result


def _browser_proved(run):
    """Has any browser of this run started? Caller holds _LOCK."""
    return run["launched_ok"] > 0 or any(os.path.exists(p) for p in run["markers"].values())


def _abandon(run_id, tid, error):
    """A target whose handling itself failed: say so on its row, and end its
    worker if it had got as far as having one."""
    _set_result(run_id, tid, {"status": "error", "detail": f"{type(error).__name__}: {error}"[:200]})
    with _LOCK:
        run = RUNS.get(run_id)
        proc = run["procs"].pop(tid, None) if run else None
        if run:
            run["markers"].pop(tid, None)
            if run.get("watch_active") == tid:
                run["watch_active"] = None
    if proc:
        try:
            proc.kill()
            proc.close()
        except Exception:
            pass


def _slot(run_id, kind, run_dir, lane):
    """One of a lane's `width` workers: take the next target until none are left."""
    while True:
        with _LOCK:
            run = RUNS.get(run_id)
            if not run or run["cancelled"] or run["fatal"] or not lane["queue"]:
                return
            hold = False
            if run["suspect"] and not _browser_proved(run):
                if not run["launching"]:
                    # A start failed, no browser of this run has come up, and
                    # none is left that could. The rest would fail the same
                    # way: stop and say why, once. A failure beside browsers
                    # that did start never gets here — it is that target's
                    # problem only, whichever lane it was in.
                    run["fatal"] = run["suspect"]
                    return
                hold = True              # siblings still starting may yet prove it
            else:
                run["suspect"] = None
                item = lane["queue"].popleft()
                run["launching"] += 1
        if hold:
            time.sleep(0.1)
            continue
        try:
            if _await_capacity(run_id):
                try:
                    _run_target(run_id, kind, run_dir, item, lane["headless"])
                finally:
                    _SLOTS.release()
        except Exception as e:
            # Whatever went wrong preparing this one target, it must not end
            # the slot: in a lane of width one that was every target after it.
            _abandon(run_id, item["target"]["id"], e)
        finally:
            with _LOCK:
                run = RUNS.get(run_id)
                if run:
                    run["launching"] -= 1


def _run_pool(run_id, kind, run_dir, lanes):
    """Drive every lane to the end, then settle the run. Every target leaves
    an artifact under run_dir, so a wrong detection rule is re-read rather
    than re-driven."""
    try:
        slots = []
        for lane in lanes:
            for _ in range(min(lane["width"], len(lane["queue"]))):
                th = threading.Thread(target=_slot, args=(run_id, kind, run_dir, lane), daemon=True)
                th.start()
                slots.append(th)
        for th in slots:
            th.join()
        with _LOCK:
            run = RUNS.get(run_id)
            # A failed start nobody has contradicted by the time everything
            # is over is the run's failure too — including a run whose only
            # target was the one that failed, which never reaches _slot's check.
            fatal = run and (run["fatal"] or (run["suspect"] if not run["launched_ok"] else None))
        if fatal:
            # Whatever stopped the run before any target could be judged.
            # Usually chromium is not installed. Without this the caller sees
            # a finished run of pending rows — a failure that looks exactly
            # like a clean "found nothing".
            _fail_run(run_id, fatal)
    except Exception as e:
        _fail_run(run_id, f"{type(e).__name__}: {e}"[:300])
        _kill_run(run_id)
    finally:
        # Nothing may stay pending once the run says it is done.
        with _LOCK:
            run = RUNS.get(run_id)
            for tid, r in (run["results"].items() if run else ()):
                if r.get("status") in ("pending", "running"):
                    run["results"][tid] = {"status": "error",
                                           "detail": "cancelled" if run["cancelled"] else "never ran"}
        _finish_run(run_id)


def _kill_run(run_id):
    with _LOCK:
        run = RUNS.get(run_id)
        live = list(run["procs"].values()) if run else []
    for p in live:
        p.kill()


def _start(kind, need_platform):
    """Shared POST handler for /verify and /discover."""
    body = request.get_json(silent=True) or {}
    raw = body.get("targets", [])
    # The operator can ask to watch the run: a visible window instead of a
    # headless one. TAGVERIFIER_HEADED=1 makes that the default.
    headed = bool(body.get("headed")) or os.environ.get("TAGVERIFIER_HEADED") == "1"
    concurrency = _concurrency(body.get("concurrency"))
    accepted, rejected = _split_targets(raw, need_platform)
    if not accepted:
        return jsonify({"error": "no usable targets", "rejected": rejected}), 400

    run_dir = core_session.new_run_dir(ARTIFACT_ROOT, campaign=kind)
    items = []
    for t in accepted:
        strategy, patience = _profile_for(t)
        items.append({"target": t, "strategy": strategy, "patience": patience})

    # Watch mode hands the browser to a person, so it needs a window to hand
    # over — there is nothing to watch in a headless one. Those targets get a
    # lane of their own, one at a time and headed, beside the headless pool.
    watch_ids = [i["target"]["id"] for i in items if i["strategy"] == "watch"]
    windowed = [i for i in items if i["strategy"] in core_strategies.NEEDS_WINDOW]
    if headed:
        # Several visible windows at once is worse than one: Chrome throttles
        # the ones behind — a video pre-roll took 232.5s hidden against 30.7s
        # in front — so "show the browser" means one at a time, in order.
        concurrency = 1
        lanes = [{"queue": collections.deque(items), "width": 1, "headless": False}]
    else:
        pool = [i for i in items if i["strategy"] not in core_strategies.NEEDS_WINDOW]
        # Longest patience first: the run ends when its slowest target does,
        # so that one should not be the last to start.
        pool.sort(key=lambda i: -i["patience"])
        lanes = [{"queue": collections.deque(pool), "width": concurrency, "headless": True},
                 {"queue": collections.deque(windowed), "width": 1, "headless": False}]

    run_id = _create_run(kind, accepted, rejected, artifacts=str(run_dir),
                         concurrency=concurrency, watch_ids=watch_ids,
                         watch_stop={tid: str(Path(run_dir) / tid / "watch.stop")
                                     for tid in watch_ids})
    _background(_run_pool, run_id, kind, run_dir, lanes)
    return jsonify({"run_id": run_id, "rejected": rejected, "artifacts": str(run_dir),
                    "watch_ids": watch_ids, "concurrency": concurrency})


# ── endpoints ────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/verify", methods=["POST", "OPTIONS"])
def start_verify():
    if request.method == "OPTIONS":
        return ("", 204)
    return _start("verify", True)


@app.route("/verify/<run_id>", methods=["GET"])
def get_progress(run_id):
    run = _read_run("verify", run_id)
    if not run:
        return jsonify({"error": "unknown run_id"}), 404
    return jsonify(run)


@app.route("/discover", methods=["POST", "OPTIONS"])
def start_discover():
    """Scan test pages for whatever ad tags they actually run.

    Same background-thread + polling shape as /verify, but no expected
    values go in: this is the step that happens *before* there is anything
    to compare against.
    """
    if request.method == "OPTIONS":
        return ("", 204)
    return _start("discover", False)


@app.route("/watch/<run_id>/done", methods=["POST", "OPTIONS"])
def end_watch(run_id):
    """The operator says they have finished clicking.

    Watch mode exists because automated clicking on these pages was wrong often
    enough to be worse than useless — so the browser is handed over, and this
    is how it comes back. Without it a watch run could only end by timing out.

    It ends the watch target running now, and only that one. The signal used
    to be one flag for the whole run, never cleared, so a second watch target
    ended the moment it started.
    """
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    with _LOCK:
        run = RUNS.get(run_id)
        if not run or not run.get("watch_ids"):
            return jsonify({"error": "unknown run_id, or it has no watch target"}), 404
        active = run.get("watch_active")
        wanted = body.get("id") or active
        if not active or wanted != active:
            return jsonify({"error": "that watch target is not the one running",
                            "watch_active": active}), 409
        # From here the operator is no longer being waited on, though the
        # window takes a moment to close: the snapshot stops naming it, and
        # a second click is answered, not refused.
        run["watch_ended"].add(active)
        stop = Path(run["watch_stop"][active])
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.touch()
    return jsonify({"ok": True})


@app.route("/cancel/<run_id>", methods=["POST", "OPTIONS"])
def cancel_run(run_id):
    """Stop the run: nothing queued starts, and every browser it has open is
    closed. Clearing the page used to leave the run going in the background —
    with ten browsers at a time, that is not something to leave running."""
    if request.method == "OPTIONS":
        return ("", 204)
    with _LOCK:
        run = RUNS.get(run_id)
        if not run:
            return jsonify({"error": "unknown run_id"}), 404
        run["cancelled"] = True
        for tid, r in run["results"].items():
            if r.get("status") == "pending":
                run["results"][tid] = {"status": "error", "detail": "cancelled before it ran"}
    _kill_run(run_id)
    return jsonify({"ok": True})


@app.route("/discover/<run_id>", methods=["GET"])
def get_discover_progress(run_id):
    run = _read_run("discover", run_id)
    if not run:
        return jsonify({"error": "unknown run_id"}), 404
    return jsonify(run)


@app.route("/match", methods=["POST", "OPTIONS"])
def start_match():
    """Pair email labels with sheet rows.

    No browser and no run id: this is pure text work and returns in one call.
    The model, if one is configured, is reached from here and only from here —
    the API key stays server-side. Rows the pipeline could not settle come
    back with needs_review set, for a person to accept or correct; nothing
    here decides whether a tag fired.
    """
    if request.method == "OPTIONS":
        return ("", 204)

    body = request.get_json(silent=True) or {}
    email_items = body.get("email_items")
    sheet_rows = body.get("sheet_rows")
    if not isinstance(email_items, list) or not isinstance(sheet_rows, list):
        return jsonify({"error": "email_items and sheet_rows must both be lists"}), 400
    if not email_items or not sheet_rows:
        return jsonify({"error": "nothing to match"}), 400

    model = ai_match.default_model()
    results = ai_match.match(email_items, sheet_rows, model=model)
    return jsonify({
        "results": results,
        "model_used": model is not None,
        "needs_review": sum(1 for r in results if r["needs_review"]),
    })


if __name__ == "__main__":
    app.run(port=8877, debug=False, threaded=True)
