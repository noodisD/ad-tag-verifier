"""API contract tests. No browser, no network.

Each test here pins a failure that actually happened and was invisible from
the UI — the run looked finished, or the row stayed pending, with nothing
said about why.

Workers are the stand-ins from conftest.py (`launcher`); test_pool.py covers
the scheduling itself.
"""
import app as api
from conftest import await_done


def test_dead_browser_is_reported_not_silently_finished(client, launcher):
    """The bug: the outer try had only `finally`, so a launch failure escaped
    into threading.excepthook. `done` flipped to true with every row still
    "pending" — indistinguishable from a clean run that found nothing."""
    launcher.plan = {"g0": "fatal"}

    r = client.post("/verify", json={"targets": [
        {"id": "g0", "url": "https://example.test/a", "platform": "Adform"}]})
    assert r.status_code == 200

    body = await_done(client, "/verify", r.get_json()["run_id"])
    assert body["error"], "a run that could not start must say so"
    assert body["results"]["g0"]["status"] == "error"
    assert body["results"]["g0"]["status"] != "pending"


def test_run_id_is_scoped_to_its_endpoint(client, launcher):
    """/verify and /discover return different shapes. Reading one on the
    other's endpoint used to return 200 with the wrong shape, which the UI
    then quietly rendered as empty rows."""
    run_id = client.post("/discover", json={
        "targets": [{"id": "t0", "url": "https://example.test/a"}]}).get_json()["run_id"]

    assert client.get(f"/discover/{run_id}").status_code == 200
    assert client.get(f"/verify/{run_id}").status_code == 404
    await_done(client, "/discover", run_id)


def test_unusable_targets_are_explained(client):
    """400 is fine; 400 with no reason is not — the UI has rows to account for."""
    r = client.post("/verify", json={"targets": [{"url": "https://example.test/a"}]})
    assert r.status_code == 400
    reasons = " ".join(x["reason"] for x in r.get_json()["rejected"])
    assert "id" in reasons and "platform" in reasons


def test_partly_unusable_batch_still_runs_and_flags_the_rest(client, launcher):
    """A dropped target used to vanish from results entirely, leaving its row
    pending forever."""
    r = client.post("/verify", json={"targets": [
        {"id": "g0", "url": "https://example.test/a", "platform": "Adform"},
        {"id": "g1", "url": "https://example.test/b"},          # no platform
    ]})
    assert r.status_code == 200
    assert [x["id"] for x in r.get_json()["rejected"]] == ["g1"]

    body = await_done(client, "/verify", r.get_json()["run_id"])
    assert body["results"]["g0"]["status"] == "done"
    assert body["results"]["g1"]["status"] == "error"
    assert "platform" in body["results"]["g1"]["detail"]


def test_malformed_payload_is_a_400_not_a_500(client):
    for payload in ({"targets": {"id": "g0"}}, {"targets": ["nope"]}, {}):
        assert client.post("/verify", json=payload).status_code == 400


def test_a_duplicate_id_is_rejected_without_clobbering_the_first(client, launcher):
    """Two targets with one id would share a folder, a HAR and a result key.
    Rejecting the second must not overwrite the first row's own result."""
    r = client.post("/discover", json={"targets": [
        {"id": "t0", "url": "https://example.test/a"},
        {"id": "T0", "url": "https://example.test/b"}]})      # same folder on Windows
    assert [x["reason"] for x in r.get_json()["rejected"]] == ["duplicate id"]
    body = await_done(client, "/discover", r.get_json()["run_id"])
    assert body["results"]["t0"]["status"] == "done"
    assert launcher.started == ["t0"]


def test_an_id_that_could_leave_the_run_folder_is_rejected(client, launcher):
    r = client.post("/discover", json={"targets": [{"id": "../x", "url": "https://example.test/a"}]})
    assert r.status_code == 400
    assert launcher.started == []


def test_ids_windows_cannot_make_a_folder_of_are_rejected(client, launcher):
    """Writing NUL\\job.json raises on Windows. That used to escape and end the
    slot's thread; "A1." and "A1" are one folder there, too."""
    r = client.post("/discover", json={"targets": [
        {"id": i, "url": "https://example.test/a"} for i in ("NUL", "con.txt", "COM1", "a.", "console")]})
    assert r.status_code == 200
    assert sorted(x["id"] for x in r.get_json()["rejected"]) == ["COM1", "NUL", "a.", "con.txt"]
    await_done(client, "/discover", r.get_json()["run_id"])
    assert launcher.started == ["console"], "a name that merely starts like one is fine"


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


def test_a_watch_target_runs_headed(client, launcher):
    """There is nothing to watch in a headless window."""
    from conftest import await_that
    launcher.plan = {"t0": "watch"}
    r = client.post("/discover", json={"targets": [{"id": "t0", "url": WATCH_URL}]})
    assert r.status_code == 200
    run_id = r.get_json()["run_id"]
    assert r.get_json()["watch_ids"] == ["t0"]
    await_that(lambda: client.get(f"/discover/{run_id}").get_json()["watch_active"] == "t0")
    client.post(f"/watch/{run_id}/done", json={"id": "t0"})
    await_done(client, "/discover", run_id)
    assert launcher.headless["t0"] is False


def test_a_normal_run_stays_headless(client, launcher):
    r = client.post("/discover", json={"targets": [{"id": "t0", "url": LOAD_URL}]})
    assert r.get_json()["watch_ids"] == []
    await_done(client, "/discover", r.get_json()["run_id"])
    assert launcher.headless["t0"] is True


def test_the_operator_can_end_a_watch(client, launcher):
    """Over HTTP there is no Ctrl+C, so without this a watch can only time out."""
    from conftest import await_that
    launcher.plan = {"t0": "watch"}
    run_id = client.post("/discover", json={
        "targets": [{"id": "t0", "url": WATCH_URL}]}).get_json()["run_id"]

    await_that(lambda: client.get(f"/discover/{run_id}").get_json()["watch_active"] == "t0")
    assert client.post(f"/watch/{run_id}/done", json={"id": "t0"}).status_code == 200
    body = await_done(client, "/discover", run_id)
    assert body["results"]["t0"].get("watched") is True, "the stop signal the capture loop polls must be set"


def test_ending_an_unknown_watch_is_a_404(client):
    assert client.post("/watch/nosuchrun/done").status_code == 404


def test_the_run_snapshot_names_the_rows_waiting_on_a_person(client, launcher):
    launcher.plan = {"t0": "watch"}
    run_id = client.post("/discover", json={
        "targets": [{"id": "t0", "url": WATCH_URL}, {"id": "t1", "url": LOAD_URL}]
    }).get_json()["run_id"]

    body = client.get(f"/discover/{run_id}").get_json()
    assert body["watch_ids"] == ["t0"]
    assert "procs" not in body and "watch_stop" not in body, "process handles must never reach JSON"
    client.post(f"/cancel/{run_id}")
    await_done(client, "/discover", run_id)
