"""
Flask API for the Tag ID Extractor frontend's "Verify" step.

POST /verify   { targets: [{id, platform, url, expected}, ...] } -> { run_id }
GET  /verify/<run_id>          -> { done, results: { <id>: {status, observed?, detail?} } }
GET  /health                   -> { ok: true }

The run happens on a background thread after the POST response returns —
same reasoning as UXAgent: the HTTP request that kicks off a run shouldn't
block on however long a batch of live page loads takes. Run state is held
in memory (RUNS), so this is a single-process, single-worker service.
"""

import threading
import uuid

from flask import Flask, jsonify, request
from playwright.sync_api import sync_playwright

from verifier import discover_target, verify_target

app = Flask(__name__)
RUNS = {}


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/verify", methods=["POST", "OPTIONS"])
def start_verify():
    if request.method == "OPTIONS":
        return ("", 204)

    targets = (request.get_json(silent=True) or {}).get("targets", [])
    targets = [t for t in targets if t.get("id") and t.get("url") and t.get("platform")]
    if not targets:
        return jsonify({"error": "no verifiable targets"}), 400

    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {
        "done": False,
        "results": {t["id"]: {"status": "pending"} for t in targets},
    }

    def worker():
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True, args=["--disable-blink-features=AutomationControlled"])
                for t in targets:
                    RUNS[run_id]["results"][t["id"]] = {"status": "running"}
                    try:
                        result = verify_target(browser, t)
                    except Exception as e:
                        result = {"status": "error", "detail": str(e)[:200]}
                    RUNS[run_id]["results"][t["id"]] = result
                browser.close()
        finally:
            RUNS[run_id]["done"] = True

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"run_id": run_id})


@app.route("/verify/<run_id>", methods=["GET"])
def get_progress(run_id):
    run = RUNS.get(run_id)
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

    targets = (request.get_json(silent=True) or {}).get("targets", [])
    targets = [t for t in targets if t.get("id") and t.get("url")]
    if not targets:
        return jsonify({"error": "no targets"}), 400

    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {
        "done": False,
        "results": {t["id"]: {"status": "pending"} for t in targets},
    }

    def worker():
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True, args=["--disable-blink-features=AutomationControlled"])
                for t in targets:
                    RUNS[run_id]["results"][t["id"]] = {"status": "running"}
                    try:
                        result = discover_target(browser, t["url"])
                    except Exception as e:
                        result = {"status": "error", "detail": str(e)[:200]}
                    RUNS[run_id]["results"][t["id"]] = result
                browser.close()
        finally:
            RUNS[run_id]["done"] = True

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"run_id": run_id})


@app.route("/discover/<run_id>", methods=["GET"])
def get_discover_progress(run_id):
    run = RUNS.get(run_id)
    if not run:
        return jsonify({"error": "unknown run_id"}), 404
    return jsonify(run)


if __name__ == "__main__":
    app.run(port=8877, debug=False)
