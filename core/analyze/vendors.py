"""What each ad vendor's beacons look like, and which ones are impressions
versus clicks.

The existing backend matches `doubleclick.net/ddm/track` as one bucket, which
cannot answer the question the tool exists to answer — "does the click
actually track?" — because an impression and a click are then the same
finding. Every vendor here is therefore split by kind.
"""

import re

# GAM's own library and ad-request endpoints live on this host. They are the
# publisher's ad *infrastructure*, not a CM360 campaign beacon, and they fire
# on every page whether or not the campaign is implemented. Counting them as
# CM360 is a false positive that makes an unimplemented tag look fine.
GAM_INFRA = "securepubads.g.doubleclick.net"

IMPRESSION = "impression"
CLICK = "click"
MEASUREMENT = "measurement"


class Vendor:
    """A vendor's beacon shapes.

    `kinds` maps a kind to (url_substring, id_regex). A URL is that kind only
    if the substring is present; the regex then pulls the campaign ID out.
    """

    def __init__(self, name, kinds, id_label):
        self.name = name
        self.id_label = id_label
        self.kinds = {k: (sub, re.compile(rx)) for k, (sub, rx) in kinds.items()}

    def classify(self, url):
        """-> (kind, id) or (None, None). Order matters: the most specific
        substring is tried first so a click URL is never read as an
        impression."""
        if GAM_INFRA in url:
            return None, None
        for kind, (sub, rx) in self.kinds.items():
            if sub in url:
                m = rx.search(url)
                return kind, (m.group(1) if m else None)
        return None, None


ADFORM = Vendor(
    "Adform",
    id_label="bn",
    kinds={
        # /C/ is the click redirector, adfserve/ the 1x1 impression counter.
        CLICK: ("track.adform.net/C/", r"[?&;]bn=(\d+)"),
        IMPRESSION: ("track.adform.net/adfserve/", r"[?&;]bn=(\d+)"),
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


VENDORS = [ADFORM, CM360, AbtShield(), DoubleVerify()]

SERVING_VENDORS = {"Adform", "CM360"}


def classify(url):
    """-> list of (vendor_name, kind, id) — a URL can only match one vendor in
    practice, but the list keeps callers simple."""
    out = []
    for v in VENDORS:
        kind, ident = v.classify(url)
        if kind:
            out.append((v.name, kind, ident))
    return out
