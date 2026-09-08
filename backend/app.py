"""
Flask API for the Tag ID Extractor frontend's "Verify" step.

POST /verify   { targets: [{id, platform, url, expected}, ...] }
                                -> { run_id, rejected: [{id, reason}] }
GET  /verify/<run_id>           -> { done, error, results: { <id>: {status, ...} } }
POST /discover { targets: [{id, url}, ...] }
                                -> { run_id, rejected: [{id, reason}] }
GET  /discover/<run_id>         -> { done, error, results }
GET  /health                    -> { ok: true }

The run happens on a background thread after the POST response returns —
same reasoning as UXAgent: the HTTP request that kicks off a run shouldn't
block on however long a batch of live page loads takes. Run state is held
in memory (RUNS), so this is a single-process, single-worker service.

Two properties matter to the caller and are easy to get wrong:

- **A run that dies still reports.** If the browser cannot start at all — by
  far the most common cause being that `playwright install chromium` was never
  run — every row would otherwise stay "pending" while `done` flips to true,
  which reads as a clean finish that found nothing.
- **A run_id belongs to one endpoint.** /verify and /discover return different
  result shapes, so looking one up on the other's endpoint is a 404, not a
  200 carrying a shape the caller cannot read.
"""

import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request
from playwright.sync_api import sync_playwright

# backend/ is run as a flat directory (`python app.py`), so put the repo root
# on the path before importing core/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine                                    # noqa: E402
from core.ai import match as ai_match           # noqa: E402
from core import profiles as core_profiles       # noqa: E402
from core.capture import session as core_session  # noqa: E402

app = Flask(__name__)

# Run state. Mutated from worker threads and read from request threads, so
# every access goes through _LOCK — reads hand back a copy, because jsonify
# serializing a dict a worker is still writing to is a RuntimeError waiting
# for the first person to add a key.
_LOCK = threading.Lock()
RUNS = {}
MAX_RUNS = 20        # nothing here is durable; cap it so a long session cannot grow forever
RUN_TTL_S = 3600

LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]

# Absolute on purpose. new_run_dir defaults to the relative "core/artifacts",
# and this process runs from backend/ — which put run artifacts in
# backend/core/artifacts/, a path .gitignore does not cover (its "core/artifacts/"
# is anchored to the repo root). HARs of live campaign pages were one
# `git add -A` away from being committed.
ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "core" / "artifacts"


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


# ── run bookkeeping ──────────────────────────────────────────────────────

def _prune_locked():
    """Drop expired runs, then cap. Caller holds _LOCK."""
    now = time.time()
    for key in [k for k, r in RUNS.items()
                if r["done"] and now - r["finished"] > RUN_TTL_S]:
        del RUNS[key]
    if len(RUNS) > MAX_RUNS:
        # Finished runs go first, oldest first; an in-flight run is only
        # evicted if there is nothing else left to drop.
        order = sorted(RUNS, key=lambda k: (not RUNS[k]["done"], RUNS[k]["created"]))
        for key in order[:len(RUNS) - MAX_RUNS]:
            del RUNS[key]


def _split_targets(raw, need_platform):
    """-> (accepted, rejected). Rejected targets are reported rather than
    dropped: silently ignoring one leaves its row pending in the UI forever
    with nothing to explain why."""
    accepted, rejected = [], []
    if not isinstance(raw, list):
        return [], [{"id": None, "reason": "targets must be a list"}]

    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            rejected.append({"id": None, "reason": f"target #{i} is not an object"})
            continue
        missing = [k for k in ("id", "url") if not t.get(k)]
        if need_platform and not t.get("platform"):
            missing.append("platform")
        if missing:
            rejected.append({"id": t.get("id"), "reason": "missing " + ", ".join(missing)})
        else:
            accepted.append(t)
    return accepted, rejected


def _strategy_for(target):
    """How profiles.yaml says this URL should be driven. Resolved here rather
    than in the worker so the launch mode is known before the browser starts."""
    try:
        return core_profiles.resolve(
            target["url"], viewport=target.get("viewport", "desktop"))["strategy"]
    except Exception:
        return "load"


def _create_run(kind, accepted, rejected):
    run_id = uuid.uuid4().hex[:12]
    results = {t["id"]: {"status": "pending"} for t in accepted}
    for r in rejected:
        if r["id"]:
            results[r["id"]] = {"status": "error", "detail": r["reason"]}
    with _LOCK:
        _prune_locked()
        RUNS[run_id] = {"kind": kind, "created": time.time(), "finished": None,
                        "done": False, "error": None, "results": results}
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
        return {"done": run["done"], "error": run["error"],
                "artifacts": run.get("artifacts"),
                # The Event itself stays put — it is not serialisable, and the
                # caller only needs to know which rows are waiting on a person.
                "watch_ids": run.get("watch_ids", []),
                "results": dict(run["results"])}


def _run_worker(run_id, targets, work, run_dir, headless=True):
    """Drive `work(browser, target, run_dir)` over the targets, recording as
    it goes. Every target leaves an artifact under run_dir, so a wrong
    detection rule is re-read rather than re-driven."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=LAUNCH_ARGS)
            try:
                for t in targets:
                    _set_result(run_id, t["id"], {"status": "running"})
                    try:
                        result = work(browser, t, run_dir)
                    except Exception as e:
                        result = {"status": "error", "detail": str(e)[:200]}
                    _set_result(run_id, t["id"], result)
            finally:
                browser.close()
    except Exception as e:
        # Whatever stopped the run before any target could be judged. Usually
        # chromium is not installed. Without this the exception disappears into
        # threading.excepthook and the caller sees a finished run of pending
        # rows — a failure that looks exactly like a clean "found nothing".
        _fail_run(run_id, f"{type(e).__name__}: {e}"[:300])
    finally:
        _finish_run(run_id)


def _start(kind, need_platform, work):
    """Shared POST handler for /verify and /discover."""
    raw = (request.get_json(silent=True) or {}).get("targets", [])
    accepted, rejected = _split_targets(raw, need_platform)
    if not accepted:
        return jsonify({"error": "no usable targets", "rejected": rejected}), 400

    run_id = _create_run(kind, accepted, rejected)
    run_dir = core_session.new_run_dir(ARTIFACT_ROOT, campaign=kind)

    # Watch mode hands the browser to a person, so it needs a window to hand
    # over — there is nothing to watch in a headless one. One watch target
    # makes the whole run headed; mixing modes in a single Playwright launch
    # is not possible, and a visible window costs the other targets nothing.
    watch_ids = [t["id"] for t in accepted if _strategy_for(t) == "watch"]
    done = threading.Event()
    for t in accepted:
        t["overrides"] = {"announce": False}
        if t["id"] in watch_ids:
            t["overrides"]["stop_check"] = done.is_set

    with _LOCK:
        if run_id in RUNS:
            RUNS[run_id]["artifacts"] = str(run_dir)
            RUNS[run_id]["watch_ids"] = watch_ids
            RUNS[run_id]["done_event"] = done

    threading.Thread(target=_run_worker,
                     args=(run_id, accepted, work, run_dir, not watch_ids),
                     daemon=True).start()
    return jsonify({"run_id": run_id, "rejected": rejected,
                    "artifacts": str(run_dir), "watch_ids": watch_ids})


# ── endpoints ────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/verify", methods=["POST", "OPTIONS"])
def start_verify():
    if request.method == "OPTIONS":
        return ("", 204)
    return _start("verify", True, engine.verify)


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
    return _start("discover", False, engine.discover)


@app.route("/watch/<run_id>/done", methods=["POST", "OPTIONS"])
def end_watch(run_id):
    """The operator says they have finished clicking.

    Watch mode exists because automated clicking on these pages was wrong often
    enough to be worse than useless — so the browser is handed over, and this
    is how it comes back. Without it a watch run could only end by timing out.
    """
    if request.method == "OPTIONS":
        return ("", 204)
    with _LOCK:
        run = RUNS.get(run_id)
        event = run.get("done_event") if run else None
    if event is None:
        return jsonify({"error": "unknown run_id, or it has no watch target"}), 404
    event.set()
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
    app.run(port=8877, debug=False)
