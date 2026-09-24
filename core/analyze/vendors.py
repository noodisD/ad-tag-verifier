"""What each ad vendor's beacons look like, and which ones are impressions
versus clicks.

The existing backend matches `doubleclick.net/ddm/track` as one bucket, which
cannot answer the question the tool exists to answer — "does the click
actually track?" — because an impression and a click are then the same
finding. Every vendor here is therefore split by kind.
"""

import re
from urllib.parse import unquote

# GAM's own library and ad-request endpoints live on this host. They are the
# publisher's ad *infrastructure*, not a CM360 campaign beacon, and they fire
# on every page whether or not the campaign is implemented. Counting them as
# CM360 is a false positive that makes an unimplemented tag look fine.
GAM_INFRA = "securepubads.g.doubleclick.net"

IMPRESSION = "impression"
CLICK = "click"
MEASUREMENT = "measurement"
# The player asking the ad server for a video creative. Deliberately not an
# impression: the VAST document is fetched before anything is shown, and a
# player that fetches it and then fails to start the spot has produced no
# impression at all. Keeping them apart is what separates "the tag is not
# implemented" from "the tag is fine, the video never played" — which on
# TVP VOD is the difference between a defect and a test environment problem.
VAST = "vast"


class Vendor:
    """A vendor's beacon shapes.

    `kinds` maps a kind to (url_substring, id_regex), or to a list of those
    when one kind arrives in more than one shape — Adform counts a display
    impression at `adfserve/` and an instream one at `videoad/impr/`, and
    both are impressions.
    """

    def __init__(self, name, kinds, id_label):
        self.name = name
        self.id_label = id_label
        self.kinds = {}
        for kind, shapes in kinds.items():
            if isinstance(shapes, tuple):
                shapes = [shapes]
            self.kinds[kind] = [(sub, re.compile(rx)) for sub, rx in shapes]

    def classify(self, url):
        """-> (kind, id) or (None, None). Order matters: the most specific
        substring is tried first so a click URL is never read as an
        impression.

        The id is looked for in the percent-decoded URL as well, because a
        click frequently arrives wrapped: Ad Manager sends
        `adclick.g.doubleclick.net/pcs/click?…&adurl=…track.adform.net/C/%3Fbn%3D90194589`,
        where the host matches but `?bn=` does not. Reading that as a click
        with no id turned a click that landed on this campaign's own tracker
        into "the slot is carrying another advertiser".
        """
        if GAM_INFRA in url:
            return None, None
        for kind, shapes in self.kinds.items():
            for sub, rx in shapes:
                if sub in url:
                    m = rx.search(url) or rx.search(unquote(url))
                    return kind, (m.group(1) if m else None)
        return None, None


ADFORM = Vendor(
    "Adform",
    id_label="bn",
    kinds={
        # /C/ is the click redirector, adfserve/ the 1x1 impression counter.
        # Display clicks go through /C/, instream ones through /videoad/c/ —
        # measured as the landing URL of a real click on a TVN pre-roll.
        CLICK: [("track.adform.net/C/", r"[?&;]bn=(\d+)"),
                ("track.adform.net/videoad/c/", r"[?&;]bn=(\d+)")],
        # Instream, measured on a TVN pre-roll, arrives in three shapes and
        # only one of them is the impression:
        #
        #   /serving/videoad/  the player asking for the VAST document
        #   /videoad/impr/     the impression, once the spot actually starts
        #   /videoad/event/    quartile and viewability events after that
        #
        # None of them look like the display rule, so before this every
        # instream placement came back "no tag fired" however correctly it
        # ran. Reading the VAST request as the impression would be the
        # opposite error: that document is fetched before anything plays, and
        # a player that fetches it and never starts the spot owes nobody an
        # impression.
        IMPRESSION: [("track.adform.net/adfserve/", r"[?&;]bn=(\d+)"),
                     ("track.adform.net/videoad/impr/", r"[?&;]bn=(\d+)")],
        VAST: ("track.adform.net/serving/videoad/", r"[?&;]bn=(\d+)"),
        MEASUREMENT: ("track.adform.net/videoad/event/", r"[?&;]bn=(\d+)"),
    },
)


CM360 = Vendor(
    "CM360",
    id_label="placement",
    kinds={
        CLICK: ("ad.doubleclick.net/ddm/trackclk/", r"B\d+\.(\d+)"),
        IMPRESSION: ("ad.doubleclick.net/ddm/trackimp/", r"B\d+\.(\d+)"),
    },
)

# ABT Shield encodes kind in the order id rather than the path, so both kinds
# share a substring and are told apart by the o= value.
ABT_IMPRESSION_ORDER = "975868942"
ABT_CLICK_ORDER = "237250412"


class AbtShield(Vendor):
    def __init__(self):
        super().__init__("ABT Shield", id_label="o",
                         kinds={IMPRESSION: ("abtshield.com/sink", r"[?&]o=(\d+)")})

    def classify(self, url):
        if "abtshield.com/sink" not in url:
            return None, None
        m = re.search(r"[?&]o=(\d+)", url)
        if not m:
            return None, None
        order = m.group(1)
        if order == ABT_CLICK_ORDER:
            return CLICK, order
        if order == ABT_IMPRESSION_ORDER:
            return IMPRESSION, order
        return MEASUREMENT, order


class DoubleVerify(Vendor):
    """Viewability measurement — rides alongside a serving tag and has no
    click side of its own."""

    HOSTS = ("pub.doubleverify.com", "cdn.doubleverify.com",
             "tps.doubleverify.com", "tpsc-ew1.doubleverify.com")

    # Config rides in the fragment on the bootstrap script (dvbm.js#cmp=…&plc=…)
    # and in the query string on visit/event calls, so the separator class has
    # to include '#'.
    PLC = re.compile(r"[?&#]plc=(\d+)")
    CMP = re.compile(r"[?&#]cmp=(\d+)")

    def __init__(self):
        super().__init__("DoubleVerify", id_label="plc", kinds={})

    def classify(self, url):
        if not any(h in url for h in self.HOSTS):
            return None, None
        m = self.PLC.search(url) or self.CMP.search(url)
        return MEASUREMENT, (m.group(1) if m else "present")


class IAS(Vendor):
    """Integral Ad Science — verification riding alongside the serving tag,
    no click side of its own.

    Unlike ABT Shield it is booked per placement: every row of a trafficking
    sheet carries its own `pubEntityId`, so which IAS tag fired says which
    placement it was implemented for, and that can be checked against the
    serving tag beside it. Two shapes, both off the sheet and the live page:

      staticjs.adsafeprotected.com/fw.js?advEntityId=3088332&pubEntityId=96486869
      pixel.adsafeprotected.com/rfw/st/3088332/96486868/skeleton.gif   (noscript)

    The script and its noscript pixel carry adjacent ids (N+1 and N) for the
    same placement; the sheet side indexes both, so either form matches.

    Matched on the host, not a substring of the whole URL — the page URL and
    other vendors' calls routinely carry `adsafeprotected.com` inside a query
    parameter, and reading those as IAS would report a tag nobody implemented.
    """

    PUB = re.compile(r"[?&#]pubEntityId=(\d+)")
    RFW = re.compile(r"/rfw/st/\d+/(\d+)/")

    def __init__(self):
        super().__init__("IAS", id_label="pubEntityId", kinds={})

    HOST = re.compile(r"^[a-z][a-z0-9+.-]*://([^/?#]*)", re.I)

    def classify(self, url):
        # Not urlsplit: it raises on a malformed netloc ("Invalid IPv6 URL" —
        # dziennik.pl makes a request with brackets in the host), and a
        # classifier that raises takes the whole capture down with it.
        m = self.HOST.match(url or "")
        host = (m.group(1) if m else "").lower().rsplit("@", 1)[-1].split(":")[0]
        if not (host == "adsafeprotected.com" or host.endswith(".adsafeprotected.com")):
            return None, None
        m = self.PUB.search(url) or self.RFW.search(url)
        return MEASUREMENT, (m.group(1) if m else "present")


VENDORS = [ADFORM, CM360, AbtShield(), DoubleVerify(), IAS()]

SERVING_VENDORS = {"Adform", "CM360"}


def classify(url):
    """-> list of (vendor_name, kind, id) — a URL can only match one vendor in
    practice, but the list keeps callers simple."""
    out = []
    for v in VENDORS:
        # One malformed URL out of the ~700 a portal page makes must never cost
        # the run: it is read as "not this vendor" and the capture carries on.
        try:
            kind, ident = v.classify(url)
        except Exception:
            continue
        if kind:
            out.append((v.name, kind, ident))
    return out
