"""Tag classification. These are the rules verdicts rest on, so they get
pinned here — every case below is one that has actually been got wrong.

Run: python -m pytest core/tests -q
"""

from core.analyze import vendors
from core.analyze.vendors import IMPRESSION, CLICK, MEASUREMENT


def kinds(url):
    return vendors.classify(url)


class TestGamInfrastructureIsNotACampaignTag:
    """GPT's library and ad requests are on doubleclick.net too. Counting them
    as CM360 makes an unimplemented campaign look implemented — the single
    most damaging false positive available here."""

    def test_gpt_library_ignored(self):
        assert kinds("https://securepubads.g.doubleclick.net/tag/js/gpt.js") == []

    def test_gampad_ad_request_ignored(self):
        assert kinds(
            "https://securepubads.g.doubleclick.net/gampad/ads?pvsid=1&correlator=2") == []

    def test_pubads_impl_ignored(self):
        assert kinds(
            "https://securepubads.g.doubleclick.net/pagead/managed/js/gpt/m1/pubads_impl.js") == []


class TestAdform:
    IMP = ("https://track.adform.net/adfserve/?bn=90069259;1x1inv=1;"
           "srctype=3;gdpr=1;ord=123456")
    CLK = "https://track.adform.net/C/?bn=90069259;gdpr=1;gdpr_consent=XYZ"

    def test_impression(self):
        assert kinds(self.IMP) == [("Adform", IMPRESSION, "90069259")]

    def test_click(self):
        assert kinds(self.CLK) == [("Adform", CLICK, "90069259")]

    def test_impression_and_click_are_not_the_same_finding(self):
        # Same bn, different kind. Collapsing these cannot answer "does the
        # click track?", which is the question the tool exists for.
        assert kinds(self.IMP)[0][1] != kinds(self.CLK)[0][1]

    def test_cookie_sync_is_not_a_beacon(self):
        assert kinds("https://c1.adform.net/serving/cookie/match?party=10013") == []

    def test_openrtb_bid_is_not_a_beacon(self):
        assert kinds("https://adx.adform.net/adx/openrtb") == []

    def test_click_variant_with_cc_prefix(self):
        assert kinds("https://track.adform.net/adfserve/?CC=1&bn=90069260;1x1inv=1") == [
            ("Adform", IMPRESSION, "90069260")]


class TestCm360:
    IMP = ("https://ad.doubleclick.net/ddm/trackimp/N1234.567890SITE/"
           "B36639324.455334468;dc_trk_aid=649061393;dc_trk_cid=263489517;ord=1")
    CLK = ("https://ad.doubleclick.net/ddm/trackclk/N1234.567890SITE/"
           "B36639324.455334468;dc_trk_aid=649061393")

    def test_impression_placement_id(self):
        assert kinds(self.IMP) == [("CM360", IMPRESSION, "455334468")]

    def test_click_placement_id(self):
        assert kinds(self.CLK) == [("CM360", CLICK, "455334468")]

    def test_favicon_noise_ignored(self):
        assert kinds("https://ad.doubleclick.net/favicon.ico?ad=300x250") == []


class TestAbtShield:
    """Kind is encoded in the order id, not the path — both look identical
    otherwise."""

    def test_impression_order(self):
        url = f"https://d1.abtshield.com/sink?o={vendors.ABT_IMPRESSION_ORDER}&sid=x&d=abc"
        assert kinds(url) == [("ABT Shield", IMPRESSION, vendors.ABT_IMPRESSION_ORDER)]

    def test_click_order(self):
        url = f"https://d1.abtshield.com/sink?o={vendors.ABT_CLICK_ORDER}&sid=x&d=abc"
        assert kinds(url) == [("ABT Shield", CLICK, vendors.ABT_CLICK_ORDER)]

    def test_unknown_order_is_measurement_not_a_verdict(self):
        url = "https://d1.abtshield.com/sink?o=111222333&sid=x"
        assert kinds(url) == [("ABT Shield", MEASUREMENT, "111222333")]


class TestDoubleVerify:
    def test_bootstrap_script_config_rides_in_the_fragment(self):
        # dvbm.js#cmp=…&plc=… — a query-only separator class misses this.
        url = "https://cdn.doubleverify.com/dvbm.js#cmp=36639324&plc=455334468"
        assert kinds(url) == [("DoubleVerify", MEASUREMENT, "455334468")]

    def test_visit_call_query_string(self):
        url = "https://tps.doubleverify.com/visit.js?ctx=1&cmp=36639324&plc=455334468"
        assert kinds(url) == [("DoubleVerify", MEASUREMENT, "455334468")]

    def test_event_pixel_without_ids_still_counts_as_present(self):
        url = "https://tpsc-ew1.doubleverify.com/event.png?impid=abc&flavor=1"
        assert kinds(url) == [("DoubleVerify", MEASUREMENT, "present")]

    def test_unrelated_host_ignored(self):
        assert kinds("https://example.com/doubleverify-guide.html") == []


class TestServingVsMeasurement:
    def test_only_adform_and_cm360_are_serving_tags(self):
        # DV and ABT ride alongside; a campaign is not "delivering" because a
        # measurement vendor fired.
        assert vendors.SERVING_VENDORS == {"Adform", "CM360"}


# ── an impression nobody asked for is not this campaign's ────────────────

from core.analyze import findings as _f


def _meta(beacons, **kw):
    m = {"beacons": beacons, "error": None, "events": []}
    m.update(kw)
    return m


def _b(kind, ident, vendor="Adform"):
    return {"vendor": vendor, "kind": kind, "id": ident, "evidence": "fired"}


def test_impression_without_an_expected_id_is_not_a_pass():
    """Measured on kobieta.wp.pl: the impressions on the page belonged to
    other advertisers while the campaign's own tag never fired. Calling that
    a pass is the false positive this tool exists to prevent."""
    r = _f.analyze(_meta([_b(_f.vendors.IMPRESSION, "455254508", "CM360")]),
                   expected_id=None, rederive=False)
    assert r["verdict"] == _f.UNATTRIBUTED
    assert r["verdict"] != _f.PASS


def test_the_same_beacon_with_a_matching_expected_id_is_a_pass():
    r = _f.analyze(_meta([_b(_f.vendors.IMPRESSION, "89750125"),
                          _b(_f.vendors.CLICK, "89750125")]),
                   expected_id="89750125", rederive=False)
    assert r["verdict"] == _f.PASS


def test_somebody_elses_tag_in_the_slot_is_named_as_that():
    r = _f.analyze(_meta([_b(_f.vendors.IMPRESSION, "455254508", "CM360")]),
                   expected_id="89750125", rederive=False)
    assert r["verdict"] == _f.WRONG_TAG
    assert "455254508" in r["other_serving_ids"]
