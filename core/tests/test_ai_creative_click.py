"""The vision fallback for clicking. No browser, no network.

Everything here guards one property: a click the tool is not sure about must
never become a pass. Four earlier targeting methods clicked other
advertisers' creatives and reported them as the campaign's — that is the
failure this module has to be incapable of repeating.
"""
from core.ai import creative_click as cc

VP = {"width": 1400, "height": 900}


class Eye:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def look(self, prompt, png):
        self.calls += 1
        self.prompt = prompt
        return self.reply


def test_a_plausible_box_is_accepted():
    box = cc.locate(Eye({"found": True, "x": 100, "y": 200, "w": 300, "h": 250,
                         "confidence": 0.9}), b"png", "SomeBrand", VP)
    assert (box["x"], box["w"]) == (100.0, 300.0)


def test_a_refusal_is_a_refusal():
    assert cc.locate(Eye({"found": False}), b"png", "SomeBrand", VP) is None


def test_no_model_means_no_guess():
    assert cc.locate(None, b"png", "SomeBrand", VP) is None


def test_without_an_advertiser_it_will_not_look():
    """With nothing to identify, "the ad" is whichever ad it happens to see."""
    eye = Eye({"found": True, "x": 1, "y": 1, "w": 300, "h": 250})
    assert cc.locate(eye, b"png", "", VP) is None
    assert eye.calls == 0


def test_boxes_that_cannot_be_a_creative_are_rejected():
    for bad in (
        {"found": True, "x": -5, "y": 10, "w": 300, "h": 250},        # off-screen
        {"found": True, "x": 1300, "y": 10, "w": 300, "h": 250},      # runs past the edge
        {"found": True, "x": 0, "y": 0, "w": 1400, "h": 890},         # the whole page
        {"found": True, "x": 10, "y": 10, "w": 5, "h": 5},            # too small
        {"found": True, "x": 10, "y": 10, "w": 0, "h": 250},          # degenerate
        {"found": True, "x": "left", "y": 10, "w": 300, "h": 250},    # not a number
    ):
        assert cc.locate(Eye(bad), b"png", "SomeBrand", VP) is None, bad


def test_the_model_may_not_break_the_run():
    class Boom:
        def look(self, *a):
            raise RuntimeError("no network")
    assert cc.locate(Boom(), b"png", "SomeBrand", VP) is None


# ── the part that makes a wrong click harmless ───────────────────────────

class Rec:
    def __init__(self, beacons):
        self.beacons = beacons


def _click(ident):
    return {"kind": "click", "evidence": "fired", "id": ident}


def test_a_click_counts_only_when_the_beacon_agrees():
    rec = Rec([_click("90069314")])
    assert cc.click_confirmed(rec, "90069314", 0) == ("confirmed", "90069314")


def test_somebody_elses_click_is_never_a_pass():
    """The slot refreshed, or the model pointed at a competitor. Either way
    this campaign's click did not track."""
    rec = Rec([_click("11112222")])
    verdict, ident = cc.click_confirmed(rec, "90069314", 0)
    assert verdict == "other_advertiser"
    assert ident == "11112222"


def test_no_beacon_is_not_a_pass_either():
    assert cc.click_confirmed(Rec([]), "90069314", 0) == ("none", None)


def test_a_beacon_from_before_the_click_does_not_count():
    """Without the index, an impression-time click tracker on the page would
    make every attempt look successful."""
    rec = Rec([_click("90069314")])
    assert cc.click_confirmed(rec, "90069314", 1) == ("none", None)


def test_impressions_are_not_mistaken_for_clicks():
    rec = Rec([{"kind": "impression", "evidence": "fired", "id": "90069314"}])
    assert cc.click_confirmed(rec, "90069314", 0) == ("none", None)


def test_markup_only_beacons_do_not_count():
    rec = Rec([{"kind": "click", "evidence": "in_markup", "id": "90069314"}])
    assert cc.click_confirmed(rec, "90069314", 0) == ("none", None)
