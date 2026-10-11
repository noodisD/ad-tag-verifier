"""
One target, in a process of its own.

The API runs every target as `python backend/worker.py <job.json>` — procs.py
says why a process and not a thread. The job file is everything the run
needs, and the result lands beside it as result.json, next to the target's
meta.json and run.har. Re-running one target by hand is the same command, so
a run that went wrong can be repeated exactly as the server drove it.

job.json: {kind: "verify"|"discover", target: {...}, run_dir, headless,
           strategy, stop_file: path|None}
"""

import json
import sys
from pathlib import Path

# backend/ is a flat directory, not a package: engine is imported by name and
# core/ through the repo root, exactly as app.py does it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


def _fatal(e):
    """The browser could not start. Marked, because the parent treats it
    differently from a page that failed: when nothing in the run has managed
    to launch, it stops the queue instead of starting sixteen more processes
    that will fail the same way."""
    return {"status": "error", "detail": f"{type(e).__name__}: {e}"[:300], "fatal": "launch"}


def run_job(job, playwright_factory=None):
    """-> the /verify or /discover result for one target. Never raises."""
    import engine
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright as playwright_factory

    work = {"verify": engine.verify, "discover": engine.discover}[job["kind"]]
    # Overrides are rebuilt here, never taken from the job: the parent's only
    # way into a run in flight is the stop file, which is a path and survives
    # the trip — the threading.Event it replaced could not be sent at all.
    target = {k: v for k, v in job["target"].items() if k != "overrides"}
    overrides = {"announce": False}
    if job.get("stop_file"):
        overrides["stop_check"] = Path(job["stop_file"]).exists
    target["overrides"] = overrides

    try:
        manager = playwright_factory()
        p = manager.__enter__()
    except Exception as e:
        return _fatal(e)
    try:
        try:
            browser = p.chromium.launch(headless=job.get("headless", True), args=LAUNCH_ARGS)
        except Exception as e:
            return _fatal(e)
        if job.get("launched_file"):
            # Tells the parent a browser can start on this machine, so one
            # sibling's failed start is not taken for "chromium is missing".
            try:
                Path(job["launched_file"]).touch()
            except Exception:
                pass
        try:
            return work(browser, target, job["run_dir"])
        except Exception as e:
            return {"status": "error", "detail": str(e)[:200]}
        finally:
            try:
                browser.close()
            except Exception:
                pass
    finally:
        try:
            manager.__exit__(None, None, None)
        except Exception:
            pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    job_path = Path(argv[0])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    result = run_job(job)
    # Written in place, not via a temp file and a rename: OneDrive holds a
    # freshly created file for a moment, and the rename then fails. A
    # half-written file reads as a crash to the parent, which is what it is.
    job_path.with_name("result.json").write_text(
        json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
