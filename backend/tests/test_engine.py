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
