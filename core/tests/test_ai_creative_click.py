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


def _click(ident, vendor="Adform"):
    return {"kind": "click", "evidence": "fired", "id": ident, "vendor": vendor}


def test_a_click_counts_only_when_the_beacon_agrees():
    rec = Rec([_click("90069314")])
    assert cc.click_confirmed(rec, "90069314", 0) == ("confirmed", "90069314")


def test_a_click_may_carry_any_of_the_sheets_ids():
    """No impression said which placement was serving, so the click has to
    carry one of the ids the sheet books — and nothing else is credited."""
    assert cc.click_confirmed(Rec([_click("B")]), ("A", "B"), 0) == ("confirmed", "B")
    assert cc.click_confirmed(Rec([_click("Z")]), ("A", "B"), 0)[0] == "other_advertiser"


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


def test_measurement_click_pixels_do_not_identify_an_advertiser():
    """ABT Shield's click pixel carries a fixed order id — 237250412 on every
    campaign of theirs — so reading it as an advertiser id turns a click that landed
    correctly into "the slot is carrying another advertiser". Measured on a
    TVN pre-roll, where the run clicked the spot, landed on
    `track.adform.net/videoad/c/?bn=90116857`, and reported it as somebody
    else's."""
    rec = Rec([_click("237250412", vendor="ABT Shield"),
               _click("90116857")])
    assert cc.click_confirmed(rec, "90116857", 0) == ("confirmed", "90116857")


def test_measurement_alone_is_not_a_click():
    rec = Rec([_click("237250412", vendor="ABT Shield")])
    assert cc.click_confirmed(rec, "90116857", 0) == ("none", None)


def test_a_click_with_nothing_expected_is_not_confirmed():
    """Measured on a moto.pl preview that never rendered this campaign's
    creative: the run clicked what was in the slot, a CM360 click tracked, and
    with no expected id it was reported as "click confirmed" — for the
    advertiser whose landing page it had just opened."""
    rec = Rec([_click("455881285", vendor="CM360")])
    verdict, ident = cc.click_confirmed(rec, None, 0)
    assert verdict == "unattributed"
    assert ident == "455881285"


# ── a click on the creative's own id, which the sheet does not book ──────
# money.pl's WP previews of the Korpo-Q4 creatives (20261009, 93b2/m0-m2):
# the creative fired Adform 90626723 and the model's click carried 90626723 —
# not in the loaded sheet, so click_confirmed said "other_advertiser".

KORPO = ("90565344", "90565351", "90571110")


def _imp(ident, vendor="Adform"):
    return {"kind": "impression", "evidence": "fired", "id": ident, "vendor": vendor}


def test_an_unbooked_id_with_its_own_impression_and_click_is_the_creatives():
    fired = [_imp("90626723"), _click("90626723"), _imp("455988298", "CM360")]
    assert cc.own_unbooked(fired, "90626723", KORPO) == ("Adform", "90626723")


def test_click_confirmed_still_calls_it_another_advertisers():
    """The report reads the pair; the click verdict itself does not change."""
    rec = Rec([_click("90626723")])
    assert cc.click_confirmed(rec, KORPO, 0) == ("other_advertiser", "90626723")


def test_a_click_with_no_impression_of_its_own_is_somebody_elses():
    assert cc.own_unbooked([_imp("90565399"), _click("90626723")], "90626723", KORPO) is None


def test_an_impression_with_no_click_proves_nothing():
    assert cc.own_unbooked([_imp("90626723")], "90626723", KORPO) is None


def test_a_booked_id_is_not_unbooked():
    assert cc.own_unbooked([_imp("90565344"), _click("90565344")], "90565344", KORPO) is None


def test_not_when_the_campaigns_own_creative_fired_too():
    """Then there was a booked creative on the page the click could have missed."""
    fired = [_imp("90565351"), _imp("90626723"), _click("90626723")]
    assert cc.own_unbooked(fired, "90626723", KORPO) is None


def test_another_vendors_pair_is_another_advertisers_creative():
    """A CM360 pre-roll on an Adform sheet (dziennik.pl, CM360 455988298):
    impression and click agree, and it is still not this campaign's."""
    fired = [_imp("455988298", "CM360"), _click("455988298", "CM360")]
    assert cc.own_unbooked(fired, "455988298", KORPO) is None


def test_the_pair_must_be_one_vendors():
    fired = [_imp("90626723", "CM360"), _click("90626723")]
    assert cc.own_unbooked(fired, "90626723", KORPO) is None


def test_measurement_pixels_are_not_a_pair():
    fired = [_imp("975868942", "ABT Shield"), _click("975868942", "ABT Shield")]
    assert cc.own_unbooked(fired, "975868942", KORPO) is None


def test_markup_only_beacons_are_not_a_pair():
    fired = [{**_imp("90626723"), "evidence": "in_markup"}, _click("90626723")]
    assert cc.own_unbooked(fired, "90626723", KORPO) is None
    assert cc.own_unbooked([_imp("90626723"), _click("90626723")], None, KORPO) is None
