"""API contract tests. No browser, no network.

Each test here pins a failure that actually happened and was invisible from
the UI — the run looked finished, or the row stayed pending, with nothing
said about why.
"""
import time

import pytest

import app as api


@pytest.fixture
def client():
    api.RUNS.clear()
    api.app.config["TESTING"] = True
    with api.app.test_client() as c:
        yield c


class _ExplodingPlaywright:
    """Stands in for a machine where `playwright install chromium` never ran."""
    def __enter__(self):
        raise RuntimeError("Executable doesn't exist at ...ms-playwright...")

    def __exit__(self, *a):
        return False


def _await_done(client, path, run_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{path}/{run_id}").get_json()
        if body["done"]:
            return body
        time.sleep(0.02)
    raise AssertionError("run never finished")


def test_dead_browser_is_reported_not_silently_finished(client, monkeypatch):
    """The bug: the outer try had only `finally`, so a launch failure escaped
    into threading.excepthook. `done` flipped to true with every row still
    "pending" — indistinguishable from a clean run that found nothing."""
    monkeypatch.setattr(api, "sync_playwright", lambda: _ExplodingPlaywright())

    r = client.post("/verify", json={"targets": [
        {"id": "g0", "url": "https://example.test/a", "platform": "Adform"}]})
    assert r.status_code == 200

    body = _await_done(client, "/verify", r.get_json()["run_id"])
    assert body["error"], "a run that could not start must say so"
    assert body["results"]["g0"]["status"] == "error"
    assert body["results"]["g0"]["status"] != "pending"


def test_run_id_is_scoped_to_its_endpoint(client, monkeypatch):
    """/verify and /discover return different shapes. Reading one on the
    other's endpoint used to return 200 with the wrong shape, which the UI
    then quietly rendered as empty rows."""
    monkeypatch.setattr(api, "sync_playwright", lambda: _ExplodingPlaywright())

    run_id = client.post("/discover", json={
        "targets": [{"id": "t0", "url": "https://example.test/a"}]}).get_json()["run_id"]

    assert client.get(f"/discover/{run_id}").status_code == 200
    assert client.get(f"/verify/{run_id}").status_code == 404


def test_unusable_targets_are_explained(client):
    """400 is fine; 400 with no reason is not — the UI has rows to account for."""
    r = client.post("/verify", json={"targets": [{"url": "https://example.test/a"}]})
    assert r.status_code == 400
    reasons = " ".join(x["reason"] for x in r.get_json()["rejected"])
    assert "id" in reasons and "platform" in reasons


def test_partly_unusable_batch_still_runs_and_flags_the_rest(client, monkeypatch):
    """A dropped target used to vanish from results entirely, leaving its row
    pending forever."""
    monkeypatch.setattr(api, "sync_playwright", lambda: _ExplodingPlaywright())

    r = client.post("/verify", json={"targets": [
        {"id": "g0", "url": "https://example.test/a", "platform": "Adform"},
        {"id": "g1", "url": "https://example.test/b"},          # no platform
    ]})
    assert r.status_code == 200
    assert [x["id"] for x in r.get_json()["rejected"]] == ["g1"]

    body = _await_done(client, "/verify", r.get_json()["run_id"])
    assert body["results"]["g1"]["status"] == "error"
    assert "platform" in body["results"]["g1"]["detail"]


def test_malformed_payload_is_a_400_not_a_500(client):
    for payload in ({"targets": {"id": "g0"}}, {"targets": ["nope"]}, {}):
        assert client.post("/verify", json=payload).status_code == 400


# ── /match ───────────────────────────────────────────────────────────────

SHEET_ROWS = [
    {"name": "Publisher_direct_300x250-Rectangle_CPC", "expected_id": "90069306"},
    {"name": "Publisher_direct_750x200-DoubleBillboard_CPC", "expected_id": "90069314"},
]


def test_match_resolves_what_it_can_and_flags_the_rest(client, monkeypatch):
    monkeypatch.setattr(api.ai_match, "default_model", lambda: None)
    r = client.post("/match", json={
        "email_items": [{"label": "300x250 Rectangle", "url": "u1"},
                        {"label": "nothing like a placement", "url": "u2"}],
        "sheet_rows": SHEET_ROWS})
    assert r.status_code == 200
    body = r.get_json()
    assert body["model_used"] is False
    assert body["results"][0]["expected_id"] == "90069306"
    assert body["results"][1]["expected_id"] is None
    assert body["needs_review"] == 1


def test_match_never_reaches_the_model_without_a_key(client, monkeypatch):
    """No key configured must mean unresolved rows, not an outbound call."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post("/match", json={
        "email_items": [{"label": "double billboard wide", "url": "u"}],
        "sheet_rows": SHEET_ROWS})
    assert r.status_code == 200
    assert r.get_json()["model_used"] is False


def test_match_rejects_a_malformed_body(client):
    for payload in ({}, {"email_items": "x", "sheet_rows": []},
                    {"email_items": [], "sheet_rows": []}):
        assert client.post("/match", json=payload).status_code == 400


# ── watch mode ───────────────────────────────────────────────────────────

WATCH_URL = "https://preview.adnami.io/creative/abc"     # profiles.yaml -> watch
LOAD_URL = "https://displayvideo.google.com/doubleclick/preview/main?creativeId=x"


def test_a_watch_target_makes_the_run_headed(client, monkeypatch):
    """There is nothing to watch in a headless window."""
    seen = {}

    def fake_worker(run_id, targets, work, run_dir, headless=True):
        seen["headless"] = headless
        api._finish_run(run_id)

    monkeypatch.setattr(api, "_run_worker",
                        lambda *a, **k: fake_worker(*a, **k))
    monkeypatch.setattr(api.threading, "Thread",
                        lambda target, args, daemon: type(
                            "T", (), {"start": lambda s: target(*args)})())

    r = client.post("/discover", json={"targets": [{"id": "t0", "url": WATCH_URL}]})
    assert r.status_code == 200
    assert r.get_json()["watch_ids"] == ["t0"]
    assert seen["headless"] is False


def test_a_normal_run_stays_headless(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(api, "_run_worker",
                        lambda run_id, t, w, d, headless=True: (
                            seen.update(headless=headless), api._finish_run(run_id)))
    monkeypatch.setattr(api.threading, "Thread",
                        lambda target, args, daemon: type(
                            "T", (), {"start": lambda s: target(*args)})())

    r = client.post("/discover", json={"targets": [{"id": "t0", "url": LOAD_URL}]})
    assert r.get_json()["watch_ids"] == []
    assert seen["headless"] is True


def test_the_operator_can_end_a_watch(client, monkeypatch):
    """Over HTTP there is no Ctrl+C, so without this a watch can only time out."""
    monkeypatch.setattr(api.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda s: None})())

    run_id = client.post("/discover", json={
        "targets": [{"id": "t0", "url": WATCH_URL}]}).get_json()["run_id"]

    event = api.RUNS[run_id]["done_event"]
    assert not event.is_set()
    assert client.post(f"/watch/{run_id}/done").status_code == 200
    assert event.is_set(), "the stop signal the capture loop polls must be set"


def test_ending_an_unknown_watch_is_a_404(client):
    assert client.post("/watch/nosuchrun/done").status_code == 404


def test_the_run_snapshot_names_the_rows_waiting_on_a_person(client, monkeypatch):
    monkeypatch.setattr(api.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda s: None})())
    run_id = client.post("/discover", json={
        "targets": [{"id": "t0", "url": WATCH_URL}, {"id": "t1", "url": LOAD_URL}]
    }).get_json()["run_id"]

    body = client.get(f"/discover/{run_id}").get_json()
    assert body["watch_ids"] == ["t0"]
    assert "done_event" not in body, "a threading.Event must never reach JSON"


def test_a_target_that_stops_answering_is_cut_off_and_the_next_one_runs(monkeypatch, tmp_path):
    """kultura.onet.pl sat for 22 minutes in a background run and held every test
    behind it. The browser is killed from outside the stuck call."""
    pytest.importorskip("psutil")
    monkeypatch.setattr(api, "TARGET_TIMEOUT_S", 4)
    api._create_run("discover", [{"id": "a"}, {"id": "b"}], [])
    run_id = next(iter(api.RUNS))

    def work(browser, target, run_dir):
        page = browser.new_page()
        if target["id"] == "a":
            page.evaluate("() => new Promise(() => {})")      # never answers
        page.close()
        return {"status": "done"}

    t0 = time.time()
    api._run_worker(run_id, [{"id": "a"}, {"id": "b"}], work, tmp_path)
    res = api.RUNS[run_id]["results"]
    assert res["a"]["status"] == "error" and "stopped responding" in res["a"]["detail"]
    assert res["b"]["status"] == "done"
    assert time.time() - t0 < 60
