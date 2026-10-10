"""Delivered, never shown: a sheet id the ad server sent that the page never requested.

The shapes are cut from real responses (ids kept, consent strings trimmed): the
dziennik.pl Ad Manager bill_top body, whose Adform impression rides in
`vu("…")` with its escapes stacked two deep; the money.pl WP ad JSON with its
protocol-relative "pixels"; a BNP Studio creative's IMPRESSION_IMG. No browser,
no network.
"""
import base64
import json

from core.analyze import findings

BS = chr(92)
GAM = ("https://securepubads.g.doubleclick.net/gampad/ads?pvsid=1&output=ldjh"
       "&iu_parts=17796319%2Cnewdz%2Cnewdz_sg%2Cbill_top&enc_prev_ius=%2F0%2F1%2F2%2F3"
       "&prev_scp=hb_bidder%3Dadform")

# vu("https://track.adform.net/adfserve/?bn\\x3d90565355;1x1inv\\x3d1") as it
# sits in the response: a JS string inside a JSON string.
VU = ('{"/17796319/newdz/newdz_sg/bill_top":["html",0,null]}\n'
      '<html><body><div data-x="1"><script>vu("https://track.adform.net/adfserve/?bn'
      + BS * 2 + 'x3d90565355;1x1inv' + BS * 2 + 'x3d1;srctype' + BS * 2 + 'x3d3")</script>'
      '<a href="https://adclick.g.doubleclick.net/pcs/click?xai=A&adurl=https://track.adform.net/C/'
      '%3Fbn%3D90565355%3Bgdpr%3D1">x</a></div></body></html>')


def _entry(url, body=None, mime="text/plain; charset=UTF-8", encoding=None):
    content = {"mimeType": mime}
    if body is not None:
        content["text"] = body
    if encoding:
        content["encoding"] = encoding
    return {"startedDateTime": "2026-10-09T09:07:25.000Z", "request": {"url": url},
            "response": {"status": 200, "content": content}}


def _har(*entries):
    return {"log": {"entries": list(entries)}}


def test_a_vu_wrapped_impression_in_a_gam_body_is_a_delivery():
    out = findings.delivered(har=_har(_entry(GAM, VU)), ids={"90565355"})
    assert out == [{"vendor": "Adform", "id": "90565355", "slot": "bill_top",
                    "source": "securepubads.g.doubleclick.net"}]


def test_the_click_link_beside_it_is_not_an_impression_delivery():
    body = '<a href="https://track.adform.net/C/?bn=90565355">x</a>'
    assert findings.delivered(har=_har(_entry(GAM, body)), ids={"90565355"}) == []


def test_once_requested_it_is_not_reported():
    fired = _entry("https://track.adform.net/adfserve/?bn=90565355;1x1inv=1;srctype=3")
    assert findings.delivered(har=_har(_entry(GAM, VU), fired), ids={"90565355"}) == []


def test_every_escape_form_is_read():
    for url in ("https://track.adform.net/adfserve/?bn" + BS + "x3d90565355;1x1inv" + BS + "x3d1",
                "https:" + BS + "/" + BS + "/track.adform.net" + BS + "/adfserve" + BS + "/?bn=90565355",
                "https://track.adform.net/adfserve/%3Fbn%3D90565355%3B1x1inv%3D1",
                "https://track.adform.net/adfserve/?bn" + BS + "u003d90565355"):
        body = '<script>vu("' + url + '")</script>'
        got = findings.delivered(har=_har(_entry(GAM, body)), ids={"90565355"})
        assert [(d["vendor"], d["id"]) for d in got] == [("Adform", "90565355")], url


def test_a_base64_body_is_read():
    b64 = base64.b64encode(VU.encode()).decode()
    got = findings.delivered(har=_har(_entry(GAM, b64, encoding="base64")), ids={"90565355"})
    assert [d["id"] for d in got] == ["90565355"]


def test_only_the_ids_asked_about():
    assert findings.delivered(har=_har(_entry(GAM, VU)), ids={"1"}) == []
    assert [d["id"] for d in findings.delivered(har=_har(_entry(GAM, VU)))] == ["90565355"]


def test_wp_pixels_are_protocol_relative():
    """money.pl / kobieta.wp.pl: WP's ad JSON writes "//track.adform.net/…"."""
    body = ('{"adm":{"creations":[{"height":600,"pixels":["//track.adform.net/adfserve/'
            '?bn=90626723;1x1inv=1;srctype=3"],"url":"https://track.adform.net/C/?bn=90626723"}]}}')
    got = findings.delivered(har=_har(_entry("https://www.money.pl/cmJoMTlm", body,
                                             mime="application/javascript")), ids={"90626723"})
    assert got == [{"vendor": "Adform", "id": "90626723", "slot": None, "source": "www.money.pl"}]


def test_a_studio_impression_img_is_a_delivery():
    body = ("{type: 'IMPRESSION_IMG',url: 'https://ad.doubleclick.net/ddm/trackimp/"
            "N1072251.6/B36818473.457786509;dc_trk_aid=1;ord=[timestamp]',scrub: 'false'}")
    head = '{"/17796319/newdz/newdz_sg/bill_top":["html"]}\n'
    got = findings.delivered(har=_har(_entry(GAM, head + body)), ids={"457786509"})
    assert [(d["vendor"], d["id"], d["slot"]) for d in got] == [("CM360", "457786509", "bill_top")]


def test_an_img_src_attribute_is_a_delivery():
    body = '<IMG SRC="https://ad.doubleclick.net/ddm/trackimp/N1.2X/B3.457786509;ord=1?" WIDTH="1">'
    got = findings.delivered(har=_har(_entry(GAM, body)), ids={"457786509"})
    assert [d["id"] for d in got] == ["457786509"]


def test_a_vast_impression_is_a_spot_that_never_played_not_a_slot_out_of_view():
    vast = ('<VAST><Ad><InLine><Impression><![CDATA[https://ad.doubleclick.net/ddm/trackimp/'
            'N1.2X/B3.455988298;ord=1]]></Impression></InLine></Ad></VAST>')
    url = GAM.replace("output=ldjh", "output=xml_vast4")
    assert findings.delivered(har=_har(_entry(url, vast, mime="text/xml; charset=UTF-8"))) == []
    # VAST text inside a JSON player config: element text, not a string or attribute
    in_json = ('{"vast":"<Impression>https://ad.doubleclick.net/ddm/trackimp/N1.2X/B3.455988298;'
               'ord=1</Impression>"}')
    assert findings.delivered(har=_har(_entry(GAM, in_json))) == []


def test_an_address_pasted_as_plain_text_is_not_a_delivery():
    """No render requests it — markup_defects names that one."""
    body = "<script>var a=1;</script> https://track.adform.net/adfserve/?bn=90484739;1x1inv=1</body>"
    assert findings.delivered(har=_har(_entry(GAM, body)), ids={"90484739"}) == []


def test_a_noscript_fallback_is_not_a_delivery():
    """DV360 previews (20260907) pair Adform's adfscript tag with a <noscript>
    adfserve pixel; where scripts run, nothing ever requests that pixel."""
    body = ('<script src="https://track.adform.net/adfscript/?bn=90123795;gdpr=;click="></script>'
            '<noscript><a href="https://track.adform.net/C/?bn=90123795">'
            '<img src="https://track.adform.net/adfserve/?bn=90123795;srctype=4;ord=635" width="320">'
            '</a></NOSCRIPT>')
    url = "https://displayads-formats.googleusercontent.com/ads/preview/content.html?client=dbm-creative"
    assert findings.delivered(har=_har(_entry(url, body, mime="text/html"))) == []
    # the same pixel outside the fallback is one
    got = findings.delivered(har=_har(_entry(url, body.replace("noscript", "div").replace("NOSCRIPT", "div"),
                                             mime="text/html")))
    assert [d["id"] for d in got] == ["90123795"]


def test_a_losing_bid_is_not_a_delivery():
    bid = '{"seatbid":[{"bid":[{"adm":"<img src=\\"https://track.adform.net/adfserve/?bn=90565355\\">"}]}]}'
    for url in ("https://adx.adform.net/adx/openrtb?rp=4", "https://fastlane.rubiconproject.com/a/api/fastlane.json",
                "https://ssp.wp.pl/bidder/bid"):
        assert findings.delivered(har=_har(_entry(url, bid)), ids={"90565355"}) == [], url


def test_one_ldjh_response_names_each_slot_on_its_own_line():
    body = ('{"/1/site/bill_top":["html"]}\n<script>vu("https://track.adform.net/adfserve/?bn=111")</script>\n'
            '{"/1/site/rectangle_1":["html"]}\n<script>vu("https://track.adform.net/adfserve/?bn=222")</script>')
    url = "https://securepubads.g.doubleclick.net/gampad/ads?iu_parts=1%2Csite%2Cbill_top%2Crectangle_1"
    got = findings.delivered(har=_har(_entry(url, body)))
    assert [(d["id"], d["slot"]) for d in got] == [("111", "bill_top"), ("222", "rectangle_1")]


def test_gam_slot_from_the_request_when_the_body_has_no_header():
    assert findings.gam_slot(GAM) == "bill_top"
    assert findings.gam_slot("https://securepubads.g.doubleclick.net/gampad/ads?"
                             "iu_parts=17796319%2Cnewdz%2Cnewdz_sg%2Cpop-up") == "pop-up"
    assert findings.gam_slot("https://example.test/ads") is None


def test_a_request_for_several_slots_names_none_without_a_header():
    """iu_parts lists every path segment once; enc_prev_ius says which slot is
    which. Its last segment is merely the last one listed."""
    multi = ("https://securepubads.g.doubleclick.net/gampad/ads?iu_parts=1%2Csite%2Cbill_top%2Crectangle_1"
             "&enc_prev_ius=%2F0%2F1%2F2%2C%2F0%2F1%2F3")
    assert findings.gam_slot(multi) is None
    one = ("https://securepubads.g.doubleclick.net/gampad/ads?iu_parts=1%2Csite%2Cbill_top%2Crectangle_1"
           "&enc_prev_ius=%2F0%2F1%2F2")
    assert findings.gam_slot(one) == "bill_top"


def test_an_unreadable_har_is_no_delivery(tmp_path):
    p = tmp_path / "run.har"
    p.write_text("{ truncated", encoding="utf-8")
    assert findings.delivered(p) == []


def test_from_a_file_as_well(tmp_path):
    p = tmp_path / "run.har"
    p.write_text(json.dumps(_har(_entry(GAM, VU))), encoding="utf-8")
    assert [d["id"] for d in findings.delivered(p, ids=["90565355"])] == ["90565355"]


# ── the stacked escapes are read everywhere, not only here ───────────────

def test_creative_tags_reads_the_double_escaped_body():
    """One pass of \\xNN left `bn\\=90565355`: creative_tags found only the click."""
    har = _har(_entry(GAM, VU.replace("bill_top", "bill_top 138621050104")))
    assert ("Adform", "impression", "90565355") in findings.creative_tags(creative_id="138621050104", har=har)


# ── DV360 previews: creativeId=xbid.N ────────────────────────────────────

DV360 = ("https://displayvideo.google.com/doubleclick/preview/main?creativeId=xbid.752653503"
         "&ecId=AOgH&eftd=1&flexHeight=600&flexWidth=300")


def test_a_dv360_preview_names_its_creative():
    assert findings.previewed_creative(DV360) == "752653503"
    assert findings.previewed_creative("https://x.test/?creativeId=138620228396&a=1") == "138620228396"
    assert findings.previewed_creative("https://x.test/?version=cbm-euro") is None


def test_creative_tags_reads_a_dv360_preview_by_its_address():
    """DV360 fetches the creative from …/752653503/previewuser; the id is in the
    address, not in the markup."""
    url = ("https://doc-0o-3c-adspreview.googleusercontent.com/preview/9o5b/jjm1/"
           "1791158400000/752653503/previewuser")
    body = '<img src="https://track.adform.net/adfserve/?bn=90484739;1x1inv=1" width="1">'
    har = _har(_entry(url, body, mime="text/html; charset=utf-8"))
    assert findings.creative_tags(creative_id="752653503", har=har) == [("Adform", "impression", "90484739")]
    assert findings.creative_tags(creative_id="111", har=har) == []
