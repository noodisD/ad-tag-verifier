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


# ── instream ─────────────────────────────────────────────────────────────
# Every URL below was recorded on a live TVN pre-roll (bn 90116857) on
# 2026-09-08. Before these rules the run reported "no tag fired" while the
# spot was playing on screen.

def test_video_vast_request_is_not_an_impression():
    """The VAST fetch says the player asked for the creative, nothing more."""
    assert vendors.classify(
        "https://track.adform.net/serving/videoad/?bn=90116857&v=42&gdpr=1"
    ) == [("Adform", vendors.VAST, "90116857")]


def test_video_impression_is_an_impression():
    assert vendors.classify(
        "https://track.adform.net/videoad/impr/?bn=90116857;rotseqno=1;smid=0;1x1inv=1"
    ) == [("Adform", vendors.IMPRESSION, "90116857")]


def test_video_quartile_events_are_measurement():
    """Quartiles ride behind the impression and must not stand in for one."""
    assert vendors.classify(
        "https://track.adform.net/videoad/event/?bn=90116857&event=27&time=0"
    ) == [("Adform", vendors.MEASUREMENT, "90116857")]


def test_display_impression_still_reads_as_one():
    """The video shapes are additional, not a replacement."""
    assert vendors.classify(
        "https://track.adform.net/adfserve/?bn=89950737;1x1inv=1;srctype=3"
    ) == [("Adform", vendors.IMPRESSION, "89950737")]


def test_video_click_uses_the_same_redirector_as_display():
    assert vendors.classify(
        "https://track.adform.net/C/?bn=90116857&cpdir=https%3A%2F%2Fexample.com"
    ) == [("Adform", vendors.CLICK, "90116857")]


def test_a_truncated_har_falls_back_to_what_was_recorded(tmp_path):
    """A HAR whose write was cut short is unparsable JSON. The run still
    happened and the recorder still saw it, so the analysis uses that rather
    than failing outright — measured on an OLX listing page whose HAR close
    had to be abandoned."""
    from core.analyze import findings
    har = tmp_path / "run.har"
    har.write_text('{"log": {"entries": [{"request": {"url": "https://track.', encoding="utf-8")
    meta = {
        "_dir": str(tmp_path), "har": "run.har", "expected_id": "90194589",
        "beacons": [{"vendor": "Adform", "kind": "impression", "id": "90194589",
                     "evidence": "fired", "url": "https://track.adform.net/adfserve/?bn=90194589"}],
    }
    r = findings.analyze(meta, expected_id="90194589", require_click=False)
    assert r["verdict"] == findings.PASS


def test_a_wrapped_click_still_names_its_campaign():
    """Ad Manager wraps the click: the Adform tracker arrives percent-encoded
    inside `adurl=`, so the host matches while `?bn=` does not. Recorded on an
    OLX ad page, where reading it as a click with no id reported a click that
    landed on this campaign's own tracker as "the slot is carrying another
    advertiser"."""
    assert vendors.classify(
        "https://adclick.g.doubleclick.net/pcs/click?xai=AKAOjs&sai=AMfl&urlfix=1"
        "&adurl=https://track.adform.net/C/%3Fbn%3D90194589%3Bgdpr%3D1"
    ) == [("Adform", vendors.CLICK, "90194589")]


def test_an_unwrapped_click_is_unaffected():
    assert vendors.classify("https://track.adform.net/C/?bn=90194589;gdpr=1") \
        == [("Adform", vendors.CLICK, "90194589")]


# ── IAS ──────────────────────────────────────────────────────────────────
# Shapes from a BNP Paribas trafficking sheet and a live dziennik.pl capture
# (2026-09-24), where the IAS script fired beside CM360 placement 457786509.

def test_ias_script_names_its_placement():
    assert vendors.classify(
        "https://staticjs.adsafeprotected.com/fw.js?advEntityId=3088332&pubEntityId=96486869"
    ) == [("IAS", vendors.MEASUREMENT, "96486869")]


def test_ias_noscript_pixel_names_its_placement():
    """The noscript pixel carries the id in the path, not the query."""
    assert vendors.classify(
        "https://pixel.adsafeprotected.com/rfw/st/3088332/96486868/skeleton.gif?gdpr=1"
    ) == [("IAS", vendors.MEASUREMENT, "96486868")]


def test_ias_call_without_an_id_is_still_ias():
    assert vendors.classify("https://dt.adsafeprotected.com/dt?anId=1") \
        == [("IAS", vendors.MEASUREMENT, "present")]


def test_a_page_url_mentioning_ias_is_not_an_ias_tag():
    """Analytics calls carry the page URL, and the page URL can carry anything.
    Matching the substring would report an IAS tag nobody implemented."""
    assert vendors.classify(
        "https://www.google.com/ccm/collect?dl=https%3A%2F%2Fstaticjs.adsafeprotected.com%2Ffw.js"
    ) == []


def test_ias_is_measurement_not_serving():
    assert "IAS" not in vendors.SERVING_VENDORS


def test_a_malformed_url_does_not_raise():
    """Recorded on dziennik.pl: a request with brackets in the host made
    urlsplit raise "Invalid IPv6 URL", and that took the whole capture down."""
    assert vendors.classify("https://[not-an-ip]/pixel?x=1") == []
    assert vendors.classify("https://staticjs.adsafeprotected.com]/fw.js?pubEntityId=1") == []


def test_one_vendor_raising_does_not_hide_the_others(monkeypatch):
    def boom(url):
        raise ValueError("broken rule")
    monkeypatch.setattr(vendors.VENDORS[-1], "classify", boom)
    assert vendors.classify("https://track.adform.net/C/?bn=90194589") \
        == [("Adform", vendors.CLICK, "90194589")]


# ── CM360's three impression forms ──────────────────────────────────────
# Seen on haps.pl / kobieta.gazeta.pl, where the creative fires the JavaScript form.

import pytest


@pytest.mark.parametrize("form", ["trackimp", "trackimpi", "trackimpj"])
def test_every_cm360_impression_form_is_an_impression(form):
    assert vendors.classify(
        f"https://ad.doubleclick.net/ddm/{form}/N1731505.148648GAZETA.PL0/B36859720.457772020;ord=1"
    ) == [("CM360", vendors.IMPRESSION, "457772020")]


def test_cm360_click_is_still_a_click():
    assert vendors.classify(
        "https://ad.doubleclick.net/ddm/trackclk/N1731505.148648GAZETA.PL0/B36989652.457781888;dc_trk_aid=1"
    ) == [("CM360", vendors.CLICK, "457781888")]


# ── a click Ad Manager wraps with its landing address fully encoded ──────
# The GAM click link on dziennik.pl's bill_top carries the Adform tracker as
# adurl=https%3A%2F%2Ftrack.adform.net%2FC%2F%3Fbn%3D… — no vendor's path is in
# the URL until it is decoded.

GAM_CLICK = "https://adclick.g.doubleclick.net/pcs/click?xai=AKAOjs&sai=AMfl&sig=Cg0A&fbs_aeid=%5Bgw_fbsaeid%5D"


def test_a_fully_encoded_adform_click_names_its_campaign():
    assert vendors.classify(
        GAM_CLICK + "&adurl=https%3A%2F%2Ftrack.adform.net%2FC%2F%3Fbn%3D90565355%3Bgdpr%3D1"
    ) == [("Adform", vendors.CLICK, "90565355")]


def test_a_fully_encoded_cm360_click_names_its_placement():
    assert vendors.classify(
        GAM_CLICK + "&adurl=https%3A%2F%2Fad.doubleclick.net%2Fddm%2Ftrackclk%2FN1234.567890SITE"
                    "%2FB36639324.455334468%3Bdc_trk_aid%3D649061393"
    ) == [("CM360", vendors.CLICK, "455334468")]


def test_a_doubly_encoded_adurl_is_read_too():
    assert vendors.classify(
        "https://googleads.g.doubleclick.net/pcs/click?xai=A"
        "&adurl=https%253A%252F%252Ftrack.adform.net%252FC%252F%253Fbn%253D90194589"
    ) == [("Adform", vendors.CLICK, "90194589")]


def test_the_search_ads_click_redirector_is_read_too():
    assert vendors.classify(
        "https://www.googleadservices.com/pagead/aclk?sa=L&ai=x"
        "&adurl=https%3A%2F%2Ftrack.adform.net%2FC%2F%3Fbn%3D90194589"
    ) == [("Adform", vendors.CLICK, "90194589")]


def test_a_view_ping_is_not_the_click_it_names():
    """/pcs/view is Ad Manager's impression ping; reading its adurl as a click
    would invent a click nobody made."""
    for host in ("securepubads.g.doubleclick.net", "googleads4.g.doubleclick.net",
                 "ad.doubleclick.net"):
        assert vendors.classify(
            f"https://{host}/pcs/view?xai=A&sig=B"
            "&adurl=https%3A%2F%2Ftrack.adform.net%2FC%2F%3Fbn%3D90565355") == []


def test_a_wrapped_landing_page_is_nobodys_click():
    assert vendors.classify(GAM_CLICK + "&adurl=https%3A%2F%2Fwww.bankclient.example%2Ffirmy%2F") == []


def test_a_sheets_ids_tell_their_serving_vendor_by_shape():
    assert vendors.serving_vendors_of(["90565344", 90571110]) == {"Adform"}
    assert vendors.serving_vendors_of(["457786509"]) == {"CM360"}
    assert vendors.serving_vendors_of(["90565344", "457786509", None, "", "abc"]) == {"Adform", "CM360"}
    assert vendors.serving_vendors_of(None) == set()
