"""The API/core bridge.

The rule pinned here is the one that would fail quietly: both sides of the
comparison must name an ID the same way.
"""
from core.analyze import findings, vendors

import engine

# Note the two different numbers: the frontend reads dc_trk_aid off this tag,
# while core keys CM360 off the number after "B…". Real CM360 tags carry both.
CM360_IMP = ("https://ad.doubleclick.net/ddm/trackimp/N1234.567890SITE/"
             "B36639324.455334468;dc_trk_aid=649061393;dc_trk_cid=263489517;ord=1")
ADFORM_IMP = "https://track.adform.net/adfserve/?bn=90069318;1x1inv=1;srctype=3"


def test_cm360_expected_id_matches_what_the_page_reader_will_find():
    """Forwarding the frontend's dc_trk_aid would make every CM360 placement
    report 'no tag fired' — the tag would be there, and we would say it was
    not."""
    target = {"id": "g0", "url": CM360_IMP, "platform": "CM360",
              "expected": {"dc_trk_aid": "649061393", "dc_trk_cid": "263489517"}}

    got = engine.expected_id(target)
    detected = vendors.classify(CM360_IMP)[0][2]

    assert got == detected, "expected id must be the one classify() produces"
    assert got != target["expected"]["dc_trk_aid"], (
        "if these ever coincide this test proves nothing — pick a fixture "
        "where they differ, as real CM360 tags do")


def test_adform_expected_id_is_the_bn():
    assert engine.expected_id({"id": "g1", "url": ADFORM_IMP}) == "90069318"


def test_falls_back_to_declared_value_for_an_unrecognised_url():
    t = {"id": "g2", "url": "https://example.test/whatever", "expected": {"bn": "123"}}
    assert engine.expected_id(t) == "123"


def test_unknown_target_yields_no_expectation_rather_than_a_guess():
    assert engine.expected_id({"id": "g3", "url": "https://example.test/x"}) is None


def test_every_core_verdict_maps_to_a_status_the_ui_can_paint():
    """A verdict with no mapping would silently render as an error pill."""
    for verdict in (findings.PASS, findings.IMPRESSION_ONLY, findings.MISSING,
                    findings.WRONG_TAG, findings.INCONCLUSIVE):
        assert verdict in engine.STATUS
        assert engine.STATUS[verdict] in ("pending", "running", "pass", "fail", "error")


def test_every_vendor_has_an_id_label_for_the_discover_payload():
    for v in vendors.VENDORS:
        assert engine.ID_LABEL.get(v.name), f"no id label for {v.name}"


def test_a_click_the_player_swallowed_is_not_an_attempt():
    """vod.tvp.pl takes the click as play/pause and the IMA SDK never sees
    it. A spot with no click tracker would still have opened the advertiser's
    page, so this says nothing about the tag — and reporting it as "clicked,
    nothing tracked" raises a defect against a tag nobody tested."""
    meta = {"events": ["video click at (692,389)",
                       "clicked (video) but no click beacon followed"],
            "click_result": "not_testable"}
    assert engine._click_attempted(meta) is False


def test_a_video_click_counts_as_an_attempt():
    """The video strategy logs "video click at (x,y)" like every other click
    path. Matching a hand-written list of sources reported a click confirmed
    by its own beacon as never attempted."""
    meta = {"events": ["video click at (692,389)",
                       "click confirmed by beacon 90116854 (video)"],
            "click_result": "confirmed"}
    assert engine._click_attempted(meta) is True


def test_the_frame_path_click_counts_too():
    """Recorded on Interia: the frame path logged "click element at (1180,723)"
    while every other path logged "<source> click at (x,y)", so twenty runs
    that had clicked reported the click as never attempted."""
    assert engine._click_attempted({"events": ["element click at (1180,723)"]}) is True


def test_the_campaigns_ids_reach_the_capture(monkeypatch, tmp_path):
    """The UI sends the sheet's ids so the capture knows when it may stop
    waiting. Dropping them here would silently restore the old behaviour —
    stopping at whoever's tag fires first."""
    seen = {}

    def fake_capture(job, browser, run_dir, viewport="desktop", overrides=None):
        seen.update(job)
        d = tmp_path / job["id"]
        d.mkdir()
        (d / "meta.json").write_text('{"id": "%s", "events": [], "beacons": []}' % job["id"],
                                     encoding="utf-8")
        return {}

    monkeypatch.setattr(engine.session, "capture", fake_capture)
    engine.discover(None, {"id": "t0", "url": "https://www.dziennik.pl/?version=cbm-gory",
                           "wait_for": ["457786509", 457783524, None, ""]}, tmp_path)
    assert seen["wait_for"] == ["457786509", "457783524"]


def _fake_capture_with(tmp_path, har_entries, beacons=(), events=(), **meta):
    import json

    def fake_capture(job, browser, run_dir, viewport="desktop", overrides=None):
        d = tmp_path / job["id"]
        d.mkdir(exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "id": job["id"], "url": job["url"], "events": list(events), "har": "run.har",
            "beacons": list(beacons), **meta}), encoding="utf-8")
        (d / "run.har").write_text(json.dumps({"log": {"entries": har_entries}}), encoding="utf-8")
        return {}
    return fake_capture


_BROKEN_IAS = ('<SCRIPT TYPE=""application/javascript"" '
               'SRC=""https://staticjs.adsafeprotected.com/fw.js?advEntityId=1&pubEntityId=1000002""></SCRIPT>')


def _entry(url, body=None, mime="text/html"):
    content = {"mimeType": mime, "text": body} if body else {"mimeType": mime}
    return {"startedDateTime": "2026-10-01T10:00:00.000Z", "request": {"url": url},
            "response": {"status": 200, "content": content}}


def test_a_tag_delivered_but_unloadable_is_reported(monkeypatch, tmp_path):
    """The scan used to say only "IAS did not fire" for a creative that carried
    the tag with doubled quotes — which sends the publisher looking for a tag
    nobody placed instead of one placed wrongly."""
    monkeypatch.setattr(engine.session, "capture", _fake_capture_with(
        tmp_path, [_entry("https://ads.example/creative", _BROKEN_IAS)]))
    out = engine.discover(None, {"id": "t0", "url": "https://pub.example/"}, tmp_path)
    assert [(d["vendor"], d["id"]) for d in out["markup_defects"] if d["tag"] == "script"] \
        == [("IAS", "1000002")]


def test_a_defect_is_dropped_when_that_tag_did_fire(monkeypatch, tmp_path):
    """If the request went out, the markup was fine in practice."""
    fired = _entry("https://staticjs.adsafeprotected.com/fw.js?advEntityId=1&pubEntityId=1000002")
    monkeypatch.setattr(engine.session, "capture", _fake_capture_with(
        tmp_path, [_entry("https://ads.example/creative", _BROKEN_IAS), fired]))
    out = engine.discover(None, {"id": "t0", "url": "https://pub.example/"}, tmp_path)
    assert [d for d in out["markup_defects"] if d["tag"] == "script"] == []


# ── what the report says when none of the sheet's ids fired ──────────────

BS = chr(92)
NOT_SEEN = "this campaign's impression NOT seen within 260s (waited for 3 sheet ids)"
KORPO = ["90565355", "90565344", "90571117"]
GAM = ("https://securepubads.g.doubleclick.net/gampad/ads?pvsid=1&output=ldjh"
       "&iu_parts=17796319%2Cnewdz%2Cnewdz_sg%2Cbill_top")
# dziennik.pl's bill_top answer: the Adform impression rides in vu("…") with
# its escapes two deep, and fires only once Ad Manager renders the slot.
BILL_TOP = ('{"/17796319/newdz/newdz_sg/bill_top":["html",0,null]}\n'
            '<html><body><script>vu("https://track.adform.net/adfserve/?bn'
            + BS * 2 + 'x3d90565355;1x1inv' + BS * 2 + 'x3d1")</script></body></html>')
OTHER_IMP = "https://ad.doubleclick.net/ddm/trackimp/N1.2X/B3.457769682;ord=1"


def _discover(monkeypatch, tmp_path, entries, wait_for=KORPO, url="https://www.dziennik.pl/",
              **meta):
    monkeypatch.setattr(engine.session, "capture", _fake_capture_with(tmp_path, entries, **meta))
    target = {"id": "t0", "url": url}
    if wait_for:
        target["wait_for"] = wait_for
    return engine.discover(None, target, tmp_path)


def test_a_delivered_sheet_id_is_named_instead_of_none_fired(monkeypatch, tmp_path):
    """dziennik.pl, 10-09: the ad server answered bill_top with the campaign's
    creative, the run waited at the top of the page, and the report said none
    of the sheet's placements fired — which reads as a missing tag."""
    out = _discover(monkeypatch, tmp_path, [_entry(GAM, BILL_TOP, mime="text/plain"),
                                            _entry(OTHER_IMP)],
                    events=[NOT_SEEN, "click skipped: no clickable creative frame found"])
    assert out["diagnosis"][0] == (
        "Adform 90565355 was delivered to slot bill_top but its impression never fired"
        " — the slot was not rendered/in view during the test")
    assert out["delivered_not_fired"] == [{"vendor": "Adform", "id": "90565355", "slot": "bill_top",
                                           "source": "securepubads.g.doubleclick.net"}]
    assert not any(d.startswith(findings.NOTHING_FIRED) for d in out["diagnosis"])
    assert "other tags that fired on the page are not in the sheet: CM360 457769682" in out["diagnosis"]
    assert not any("none this campaign books" in d for d in out["diagnosis"])


def test_a_delivery_that_fired_after_all_is_not_reported(monkeypatch, tmp_path):
    out = _discover(monkeypatch, tmp_path, [
        _entry(GAM, BILL_TOP, mime="text/plain"),
        _entry("https://track.adform.net/adfserve/?bn=90565355;1x1inv=1;srctype=3")],
        events=[NOT_SEEN])
    assert out["delivered_not_fired"] == []
    assert not any("was delivered" in d for d in out["diagnosis"])


def test_a_booked_impression_after_the_wait_drops_none_fired(monkeypatch, tmp_path):
    """f8a5/t4: 90571117 fired at 305s, once the vision pass scrolled bill_top
    into view, and its click was confirmed — next to "none of the sheet's
    placements fired within 260s"."""
    out = _discover(monkeypatch, tmp_path, [
        _entry("https://track.adform.net/adfserve/?bn=90571117;1x1inv=1"),
        _entry("https://track.adform.net/C/?bn=90571117;gdpr=1")],
        events=[NOT_SEEN, "click confirmed by beacon 90571117 (frame)"], click_result="confirmed")
    assert not any(d.startswith(findings.NOTHING_FIRED) for d in out["diagnosis"])
    assert out["working_unbooked"] == []


# The welovemedia creative as DV360 previews it: the Adform impression pasted
# after </script> as bare text, never requested; the click works.
WELOVEMEDIA = ("<html><body><script>var clickTag = 'https://adclick.g.doubleclick.net/pcs/click"
               "?xai=A&adurl=https://track.adform.net/C/?bn=90484739';</script> "
               "https://track.adform.net/adfserve/?bn=90484739;1x1inv=1;srctype=3;ord=[timestamp]"
               "</body></html>")
DV360 = ("https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.752653503"
         "&flexHeight=600&flexWidth=300")
PREVIEW = ("https://doc-0o-3c-adspreview.googleusercontent.com/preview/9o5b/1791158400000/"
           "752653503/previewuser")


def test_a_tracker_pasted_as_text_is_named_as_the_cause(monkeypatch, tmp_path):
    out = _discover(monkeypatch, tmp_path, [
        _entry(PREVIEW, WELOVEMEDIA), _entry("https://track.adform.net/C/?bn=90484739")],
        wait_for=["90484739"], url=DV360, click_result="confirmed",
        events=["this campaign's impression NOT seen within 45s (waited for 1 sheet ids)",
                "click confirmed by beacon 90484739 (frame)"])
    assert out["diagnosis"][0] == ("Adform 90484739 impression: tracker URL pasted as plain text"
                                   " — no browser will request it")
    assert [(d["vendor"], d["kind"], d["id"], d["tag"]) for d in out["markup_defects"]] == [
        ("Adform", "impression", "90484739", "text")]
    # neither a slot out of view nor a missing tag
    assert out["delivered_not_fired"] == []
    assert not any(d.startswith(findings.NOTHING_FIRED) for d in out["diagnosis"])


def test_without_a_sheet_no_impression_fired_stays(monkeypatch, tmp_path):
    """With no sheet, a broken tag on the page may be anybody's."""
    out = _discover(monkeypatch, tmp_path, [_entry("https://ads.example/creative", WELOVEMEDIA)],
                    wait_for=None, events=["an impression NOT seen within 45s"])
    assert "no impression fired within 45s" in out["diagnosis"]
    assert out["delivered_not_fired"] == [] and out["working_unbooked"] == []


def test_a_dv360_preview_names_the_tags_its_creative_carries(monkeypatch, tmp_path):
    body = '<img src="https://track.adform.net/adfserve/?bn=90484700;1x1inv=1" width="1">'
    out = _discover(monkeypatch, tmp_path, [
        _entry(PREVIEW, body), _entry("https://track.adform.net/adfserve/?bn=90484700;1x1inv=1")],
        wait_for=["90484739"], url=DV360, events=[NOT_SEEN])
    assert out["diagnosis"][0] == ("the previewed creative (creativeId 752653503) carries "
                                   "Adform 90484700, which the sheet does not book")


# money.pl's WP previews of the Korpo-Q4 creatives (93b2/m0): the creative
# fired Adform 90626723, the model's click carried 90626723, and the sheet
# does not book it.
WP_IMP = "https://track.adform.net/adfserve/?bn=90626723;1x1inv=1;srctype=3"
WP_CLICK = "https://track.adform.net/C/?bn=90626723;gdpr=1"


def _other(source, ident):
    return [NOT_SEEN, f"{source} click at (195,767)",
            f"click tracked for a DIFFERENT id ({ident}) — not this campaign; "
            "the slot is carrying another advertiser"]


def test_a_click_on_the_creatives_own_unbooked_id_says_the_creative_works(monkeypatch, tmp_path):
    out = _discover(monkeypatch, tmp_path, [_entry(WP_IMP), _entry(WP_CLICK)],
                    events=_other("model", "90626723"), click_result="other_advertiser")
    assert out["working_unbooked"] == [{"vendor": "Adform", "id": "90626723"}]
    assert out["diagnosis"][0] == ("the creative works — impression and click both carry "
                                   "Adform 90626723 — but the sheet does not book 90626723")
    assert "the click landed on another advertiser's creative" not in out["diagnosis"]
    assert not any("none this campaign books" in d for d in out["diagnosis"])
    assert out["click_result"] == "other_advertiser"     # the click's own verdict is kept


def test_a_click_aimed_at_an_unbooked_frame_is_the_same_finding(monkeypatch, tmp_path):
    """The capture clicks the frame of an impression from the sheet's vendor
    under an id the sheet lacks, judged against that id."""
    out = _discover(monkeypatch, tmp_path, [_entry(WP_IMP), _entry(WP_CLICK)],
                    events=[NOT_SEEN, "trying the frame of Adform 90626723, which fired here "
                                      "but is not in the sheet", "element click at (150,300)",
                            "click confirmed by beacon 90626723 (unbooked)"],
                    click_result="confirmed")
    assert out["working_unbooked"] == [{"vendor": "Adform", "id": "90626723"}]
    assert out["diagnosis"][0].startswith("the creative works")


def test_a_genuinely_different_click_keeps_its_verdict(monkeypatch, tmp_path):
    out = _discover(monkeypatch, tmp_path, [_entry(WP_IMP),
                                            _entry("https://track.adform.net/C/?bn=11112222")],
                    events=_other("model", "11112222"), click_result="other_advertiser")
    assert out["working_unbooked"] == []
    assert "the click landed on another advertiser's creative" in out["diagnosis"]


def test_a_frame_clicked_for_being_an_ad_proves_nothing(monkeypatch, tmp_path):
    """The element path took whichever impression's frame came first; that it
    tracked its own id says nothing about whose creative it was."""
    out = _discover(monkeypatch, tmp_path, [_entry(WP_IMP), _entry(WP_CLICK)],
                    events=_other("element", "90626723"), click_result="other_advertiser")
    assert out["working_unbooked"] == []
    assert "the click landed on another advertiser's creative" in out["diagnosis"]


def test_another_vendors_pair_stays_another_advertisers(monkeypatch, tmp_path):
    """A CM360 creative clicked on an Adform sheet's test: impression and
    click agree, and it is still somebody else's."""
    out = _discover(monkeypatch, tmp_path, [
        _entry("https://ad.doubleclick.net/ddm/trackimp/N1.2X/B3.455988298;ord=1"),
        _entry("https://ad.doubleclick.net/ddm/trackclk/N1.2X/B3.455988298;dc_trk_aid=1")],
        events=_other("model", "455988298"), click_result="other_advertiser")
    assert out["working_unbooked"] == []
    assert "the click landed on another advertiser's creative" in out["diagnosis"]
