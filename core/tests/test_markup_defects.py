"""A tag can be delivered and still never load. These pin the rule that finds it.

The shapes are copied from two real creatives seen in two days on different
publishers (ids replaced): an IAS snippet pasted with CSV-style escaping, so
`SRC="https://…"` arrives as `SRC=""https://…""`. HTML reads `src=""` as empty,
the script has no address, and the only symptom is a tag that never fires.
"""
import json

from core.analyze import findings

BROKEN = ('<IMG SRC="https://ad.doubleclick.net/ddm/trackimp/N1.2X/B3.4567;ord=1?" '
          'BORDER="0" HEIGHT="1" WIDTH="1">\n'
          '<SCRIPT TYPE=""application/javascript"" '
          'SRC=""https://staticjs.adsafeprotected.com/fw.js?advEntityId=1&pubEntityId=1000002""></SCRIPT>\n'
          '<NOSCRIPT><IMG SRC=""https://pixel.adsafeprotected.com/rfw/st/1/1000001/skeleton.gif"" '
          'BORDER=0></NOSCRIPT>')

HEALTHY = BROKEN.replace('""', '"')


def _har(tmp_path, *bodies, mime="text/html", encoding=None):
    entries = []
    for i, body in enumerate(bodies):
        content = {"mimeType": mime, "text": body}
        if encoding:
            content["encoding"] = encoding
        entries.append({"startedDateTime": "2026-10-01T10:00:00.%03dZ" % i,
                        "request": {"url": f"https://ads.example/{i}"},
                        "response": {"status": 200, "content": content}})
    p = tmp_path / "run.har"
    p.write_text(json.dumps({"log": {"entries": entries}}), encoding="utf-8")
    return p


def test_doubled_quotes_make_the_script_unloadable(tmp_path):
    out = findings.markup_defects(_har(tmp_path, BROKEN))
    scripts = [d for d in out if d["tag"] == "script"]
    assert [(d["vendor"], d["id"]) for d in scripts] == [("IAS", "1000002")]
    assert "doubled quotes" in scripts[0]["problem"]


def test_the_noscript_pixel_is_reported_with_its_own_id(tmp_path):
    out = findings.markup_defects(_har(tmp_path, BROKEN))
    assert ("IAS", "1000001", "img") in [(d["vendor"], d["id"], d["tag"]) for d in out]


def test_a_well_formed_tag_is_not_a_defect(tmp_path):
    assert findings.markup_defects(_har(tmp_path, HEALTHY)) == []


def test_the_same_defect_is_reported_once(tmp_path):
    out = findings.markup_defects(_har(tmp_path, BROKEN, BROKEN, BROKEN))
    assert len([d for d in out if d["tag"] == "script"]) == 1


def test_markup_arriving_percent_encoded_and_hex_escaped_is_read(tmp_path):
    """DV360's preview page hands the creative over as an encoded JS string."""
    from urllib.parse import quote
    encoded = quote(BROKEN.replace("<", "\\x3c").replace(">", "\\x3e"), safe="")
    # the page itself keeps the host readable; only punctuation is encoded
    encoded = encoded.replace("staticjs.adsafeprotected.com", "staticjs.adsafeprotected.com")
    out = findings.markup_defects(_har(tmp_path, "var c = '" + encoded + "';"))
    assert ("IAS", "1000002") in [(d["vendor"], d["id"]) for d in out]


def test_a_base64_body_is_decoded(tmp_path):
    import base64
    b64 = base64.b64encode(BROKEN.encode()).decode()
    out = findings.markup_defects(_har(tmp_path, b64, encoding="base64"))
    assert any(d["id"] == "1000002" for d in out)


def test_images_are_not_searched(tmp_path):
    assert findings.markup_defects(_har(tmp_path, BROKEN, mime="image/gif")) == []


def test_a_host_we_do_not_know_is_not_reported(tmp_path):
    other = '<SCRIPT SRC=""https://cdn.example.org/lib.js""></SCRIPT> adform'
    assert findings.markup_defects(_har(tmp_path, other)) == []


def test_an_unreadable_har_is_not_a_crash(tmp_path):
    p = tmp_path / "run.har"
    p.write_text("{ truncated", encoding="utf-8")
    assert findings.markup_defects(p) == []


# ── diagnose: the identified reason, in words ───────────────────────────

def _meta(*events, error=None):
    return {"events": list(events), "error": error}


def test_a_creative_that_was_never_served_says_so():
    out = findings.diagnose(_meta(
        "this campaign's impression NOT seen within 90s (waited for 20 sheet ids)",
        "click skipped: none of this campaign's creatives appeared, so there was nothing of ours to click"))
    assert out == ["the campaign's creative was never served within 90s"]


def test_a_missing_click_is_not_listed_as_a_second_problem_when_nothing_was_served():
    out = findings.diagnose(_meta(
        "an impression NOT seen within 45s",
        "model could not locate the creative",
        "click skipped: no clickable creative frame found"))
    assert out == ["the campaign's creative was never served within 45s"]


def test_a_click_that_tracked_nothing_is_named():
    out = findings.diagnose(_meta("this campaign's impression seen within 100s",
                                  "clicked (model) but no click beacon followed"))
    assert out == ["the creative was clicked but no click beacon followed"]


def test_a_click_on_another_advertiser_is_named():
    out = findings.diagnose(_meta(
        "click tracked for a DIFFERENT id (425907911) — not this campaign; the slot is carrying another advertiser"))
    assert out == ["the click landed on another advertiser's creative"]


def test_a_late_load_is_named_with_its_limit():
    out = findings.diagnose(_meta("page did not finish loading within 60s — carrying on with what has loaded"))
    assert out == ["the page took longer than 60s to finish loading"]


def test_a_failed_run_gives_its_error():
    out = findings.diagnose(_meta(error="ValueError: boom\nCall log:\n  - x"))
    assert out == ["the run stopped with an error: ValueError: boom"]


def test_a_clean_run_has_nothing_to_diagnose():
    assert findings.diagnose(_meta("this campaign's impression seen within 100s",
                                   "click confirmed by beacon 1 (frame)")) == []


def test_a_bot_check_wall_is_found_in_the_har(tmp_path):
    har = tmp_path / "run.har"
    har.write_text(json.dumps({"log": {"entries": [
        {"request": {"url": "https://pub.example/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1?ray=1"},
         "response": {"status": 200, "content": {}}}]}}), encoding="utf-8")
    assert findings.diagnose(_meta(), har_path=har)[0].startswith("the page served a bot-check wall")


def test_an_ordinary_page_is_not_a_bot_check(tmp_path):
    har = tmp_path / "run.har"
    har.write_text(json.dumps({"log": {"entries": [
        {"request": {"url": "https://pub.example/article"},
         "response": {"status": 200, "content": {}}}]}}), encoding="utf-8")
    assert findings.diagnose(_meta(), har_path=har) == []


def test_nothing_to_click_and_nothing_found_is_one_cause_not_two():
    out = findings.diagnose(_meta("this campaign's impression seen within 100s",
                                  "model could not locate the creative (looked through 5 screens)",
                                  "click skipped: no clickable creative frame found"))
    assert out == ["the vision check could not find the creative on screen"]
