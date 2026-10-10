"""Artifact -> verdict. Pure functions, no browser.

Everything here can run against artifacts captured days ago. That is the point
of the split: when a detection rule turns out to be wrong — and several have
been — the fix is re-running this over stored HARs in a second, not re-driving
twenty publisher pages for ten minutes and hoping the same ads serve again.
"""

import base64
import json
import re
from pathlib import Path
from urllib.parse import unquote

from core.analyze import vendors

# verdict values
PASS = "pass"
IMPRESSION_ONLY = "impression_only"
MISSING = "missing"
WRONG_TAG = "wrong_tag"
INCONCLUSIVE = "inconclusive"
# Something fired, but nothing said which ID was supposed to. Kept apart from
# PASS because "an impression happened" and "this campaign's impression
# happened" are different claims: measured on kobieta.wp.pl, the impressions
# on the page belonged to two unrelated advertisers while the campaign's
# own Adform tag never fired at all, and reporting that as a pass is exactly
# the false positive this tool exists to prevent.
UNATTRIBUTED = "unattributed"


def read_har(har_path):
    """-> the parsed HAR, or None when it is missing or unreadable.

    A discover run reads one HAR five ways (beacons, defects, deliveries, the
    bot check, the previewed creative's tags); on a 60 MB portal capture
    parsing it once instead of five times is the difference that matters.
    """
    try:
        with open(har_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load(har_path, har):
    if har is not None:
        return har
    return read_har(har_path) if har_path else None


def beacons_from_har(har_path=None, har=None):
    """Re-derive beacons straight from the HAR.

    Independent of whatever the recorder believed at capture time, so a
    corrected vendor pattern applies retroactively to every artifact already
    on disk. Raises on an unreadable file — callers fall back to what the
    recorder saw.
    """
    if har is None:
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)

    entries = har.get("log", {}).get("entries", [])
    t0 = None
    out, seen = [], set()

    for e in entries:
        url = e.get("request", {}).get("url", "")
        started = e.get("startedDateTime")
        if t0 is None:
            t0 = started
        for vendor, kind, ident in vendors.classify(url):
            key = (vendor, kind, ident)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "vendor": vendor, "kind": kind, "id": ident,
                "url": url, "evidence": "fired",
                "started": started,
                "status": e.get("response", {}).get("status"),
            })
    return out


def load_artifact(run_dir):
    run_dir = Path(run_dir)
    with open(run_dir / "meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    meta["_dir"] = str(run_dir)
    return meta


# ── tags that are delivered but cannot load ──────────────────────────────

# Hosts worth looking for. A response body is only searched when one of them
# appears in it, so a 3 MB script bundle costs a substring test, not a regex.
# "doubleclick.net", not "doubleclick.net/ddm": inside an escaped JS string the
# path arrives as `doubleclick.net\/ddm` or `doubleclick.net%2Fddm`.
_TAG_HOSTS = ("adsafeprotected", "doubleclick.net", "adform.net",
              "doubleverify", "abtshield")

# <script src=""https://…""> — the attribute value wrapped in a second pair of
# quotes. HTML reads `src=""` as an empty value and the address that follows as
# a stray attribute name, so the element has no source and nothing is requested.
_DOUBLED = re.compile(
    r"<\s*(script|img|iframe)\b[^<>]*?\bsrc\s*=\s*\"\"\s*(https?://[^\"'<>\s]+?)\"\"",
    re.IGNORECASE)

_BS = re.escape(chr(92))
# Escapes come stacked: the dziennik.pl Ad Manager body carries the creative's
# vu() call as `bn\\x3d90565355` — a JS string inside a JSON string — and one
# pass of \xNN left `bn\=90565355`, which no vendor rule reads as an id.
_HEX = re.compile(_BS + r"+x([0-9a-fA-F]{2})")
_UNI = re.compile(_BS + r"+u([0-9a-fA-F]{4})")
_SLASH = re.compile(_BS + r"+/")


def _uni(m):
    n = int(m.group(1), 16)
    # A lone surrogate is not a character; leave the escape as it was.
    return m.group(0) if 0xD800 <= n <= 0xDFFF else chr(n)


def _readable(text):
    """Undo the layers a creative can arrive in: percent-encoding (DV360's
    preview page hands the markup over as an encoded JS string), \\xNN and
    \\uNNNN escapes and escaped slashes, however many backslashes deep."""
    # Any %XX, not just an encoded "<": the markup may arrive with its angle
    # brackets already turned into \x3c first, leaving no %3C to key on.
    if re.search(r"%[0-9A-Fa-f]{2}", text):
        text = unquote(text)
    if chr(92) not in text:
        return text
    text = _HEX.sub(lambda m: chr(int(m.group(1), 16)), text)
    text = _UNI.sub(_uni, text)
    return _SLASH.sub("/", text)


def _body(entry):
    """-> the response text of one HAR entry worth searching, or ""."""
    content = entry.get("response", {}).get("content", {}) or {}
    mime = (content.get("mimeType") or "").lower()
    if mime.startswith(("image/", "video/", "audio/", "font/")):
        return ""
    text = content.get("text") or ""
    if text and content.get("encoding") == "base64":
        try:
            text = base64.b64decode(text).decode("utf-8", "replace")
        except Exception:
            return ""
    return text


def _mime(entry):
    return ((entry.get("response", {}).get("content", {}) or {}).get("mimeType") or "").lower()


# Any address in readable markup, protocol-relative ones included (WP's ad JSON
# writes its pixels as "//track.adform.net/…").
_ANY_URL = re.compile(r"(?:https?:)?//[^\s\"'<>\\]+", re.IGNORECASE)

# Elements whose content is rendered as text. A tracker address standing as
# text right after one of these opens, or after an element closes, is a text
# node: the page shows it (or nothing, in a 1x1 frame) and never requests it.
# Kept to HTML on purpose — VAST's <Impression>https://…</Impression> has the
# same shape and is exactly how a video tracker is meant to be written; so is
# a tag shown for reading in a <pre> or <textarea>.
_TEXT_PARENTS = {"html", "body", "div", "span", "p", "center", "td", "th", "li",
                 "font", "b", "i", "u", "em", "strong", "section", "article",
                 "header", "footer", "main", "ins", "a", "label", "small"}
_VOID = {"img", "br", "hr", "meta", "link", "input", "wbr", "source", "embed",
         "param", "base", "area", "col", "track"}
_CLOSABLE = _TEXT_PARENTS | {"script", "noscript", "style", "iframe", "table",
                             "tr", "tbody", "thead", "ul", "ol", "object", "video",
                             "audio", "svg", "canvas", "form", "button", "head",
                             "h1", "h2", "h3", "h4", "h5", "h6", "nav", "aside",
                             "figure", "picture"}
_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)\b([^<>]*)>")


def _as_text(text, start, end):
    """Does the address at text[start:end] stand in the markup as plain text —
    outside every attribute, script string and call — rather than somewhere a
    browser would request it from?

    The shape, from DV360 previews of the welovemedia creatives: the Adform
    impression URL pasted after the creative's closing tag,
    `…</script> https://track.adform.net/adfserve/?bn=90484739;…</body>`. HTML
    renders that as text; nothing ever asks for it.
    """
    j = start - 1
    while j >= 0:
        if text[j].isspace():
            j -= 1
        elif j >= 1 and text[j - 1] == chr(92) and text[j] in "nrt":
            j -= 2                       # an escaped newline inside a JS string
        else:
            break
    if j < 0 or text[j] != ">":
        return False                     # a quote, '=', '(' …: requested from code
    lt = text.rfind("<", 0, j)
    m = _TAG.fullmatch(text, lt, j + 1) if lt >= 0 else None
    if not m:
        return False
    closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
    if attrs.count('"') % 2 or attrs.count("'") % 2:
        return False                     # the '>' sits inside an attribute value
    if closing:
        if name not in _CLOSABLE:
            return False
    elif name not in _TEXT_PARENTS and name not in _VOID:
        return False                     # inside <script>, <textarea>, <pre>, VAST …
    k = end
    while k < len(text) and text[k].isspace():
        k += 1
    # Followed by the next tag, or by the end of the string the markup is in.
    return k >= len(text) or text[k] in "<'\""


PLAIN_TEXT = "tracker URL pasted as plain text — no browser will request it"


def markup_defects(har_path=None, har=None):
    """Vendor tags present in delivered markup that the browser cannot load.

    The commonest cause, seen twice in two days on different publishers: a tag
    pasted into a creative with CSV-style escaping, so
    `SRC="https://staticjs.adsafeprotected.com/fw.js?…"` arrives as
    `SRC=""https://staticjs.adsafeprotected.com/fw.js?…""`. The script has no
    address, no request is made, and the only symptom is a tag that never fires
    — indistinguishable, from the traffic alone, from one nobody implemented.
    The HAR holds the response bodies, so the cause can be read off directly.

    The second: an impression or measurement tracker's address pasted into the
    creative as bare text, with no <img> or <script> around it (tag "text").
    Eleven DV360 previews of the welovemedia creatives carried their Adform
    impression that way — a trafficking error that, from the traffic alone,
    reads exactly like a tag nobody implemented.

    -> [{"vendor", "kind", "id", "tag", "problem", "url"}], deduplicated.
    Whether the tag *also* fired is the caller's to check against the beacons.
    """
    har = _load(har_path, har)
    if har is None:
        return []

    out, seen = [], set()

    def add(vendor, kind, ident, tag, url, problem):
        key = (vendor, ident, tag)
        if key in seen:
            return
        seen.add(key)
        out.append({"vendor": vendor, "kind": kind, "id": ident, "tag": tag,
                    "url": url[:200], "problem": problem})

    for e in har.get("log", {}).get("entries", []):
        text = _body(e)
        if not text:
            continue
        low = text.lower()
        if not any(h in low for h in _TAG_HOSTS):
            continue
        readable = _readable(text)
        for m in _DOUBLED.finditer(readable):
            tag, url = m.group(1).lower(), m.group(2)
            for vendor, kind, ident in vendors.classify(url):
                add(vendor, kind, ident, tag, url,
                    "the tag is delivered with its attribute wrapped in doubled "
                    "quotes, so its address is empty and the browser never requests it")
        # VAST writes every tracker as element text: its format, not a defect.
        if "xml" in _mime(e):
            continue
        for m in _ANY_URL.finditer(readable):
            url = m.group(0)
            full = "https:" + url if url.startswith("//") else url
            # A click address is not meant to be requested until someone clicks.
            hits = [h for h in vendors.classify(full)
                    if h[1] in (vendors.IMPRESSION, vendors.MEASUREMENT)]
            if hits and _as_text(readable, m.start(), m.end()):
                for vendor, kind, ident in hits:
                    add(vendor, kind, ident, "text", full, PLAIN_TEXT)
    return out


# ── delivered, never shown ───────────────────────────────────────────────

# Responses that carry a creative but do not place it: a header-bidding bid
# that may have lost the auction, a tag-manager container, a video player's
# playlist. A tracker in one of these says nothing about what reached a slot.
_NOT_A_DELIVERY = ("bidder", "/openrtb", "prebid", "rubiconproject.com",
                   "adx.adform.net", "connectad.io", "nexx360.io",
                   "googletagmanager.com", "onnetwork.tv")

_SERVING_URL = re.compile(
    r"(?:https?:)?//(?:track\.adform\.net|ad\.doubleclick\.net)/[^\s\"'<>\\]*",
    re.IGNORECASE)

# One Ad Manager "ldjh" response can fill several slots; each starts on its
# own line with {"/<network>/<path>/<slot>":[…
_GAM_SLOT_HEAD = re.compile(r'(?:^|\n)\{"(/[^"\n]+)":\[')

# The fallback a tag carries for browsers without JavaScript. Its <img> is
# never requested where scripts run — DV360 previews (20260907) pair Adform's
# adfscript tag with a <noscript> adfserve pixel that no run could fire.
_NOSCRIPT = re.compile(r"<noscript\b.*?</noscript\s*>", re.IGNORECASE | re.DOTALL)


def gam_slot(req_url, text=None, pos=None):
    """The ad unit's last path segment (bill_top, rectangle_1, pop-up) for a
    position in an Ad Manager response, or None.

    The header line just before the position names the slot. A single-slot
    request names it in `iu_parts` too, which is the fallback: `enc_prev_ius`
    (/0/1/2/3) indexes the slot's path into `iu_parts`, one path per slot. A
    request for several slots with no header to tell them apart names none.
    """
    if text is not None and pos is not None:
        head = None
        for head in _GAM_SLOT_HEAD.finditer(text, 0, pos):
            pass
        if head:
            return head.group(1).rstrip("/").rsplit("/", 1)[-1] or None
    m = re.search(r"[?&]iu_parts=([^&]*)", req_url or "")
    if m:
        parts = unquote(m.group(1)).split(",")
        e = re.search(r"[?&]enc_prev_ius=([^&]*)", req_url)
        if not e:
            return parts[-1] or None
        paths = unquote(e.group(1)).split(",")
        last = paths[0].rstrip("/").rsplit("/", 1)[-1]
        if len(paths) != 1 or not last.isdigit() or int(last) >= len(parts):
            return None
        return parts[int(last)] or None
    m = re.search(r"[?&]iu=([^&]*)", req_url or "")
    if m:
        return unquote(m.group(1)).rstrip("/").rsplit("/", 1)[-1] or None
    return None


def _host(url):
    m = re.match(r"^[a-z][a-z0-9+.-]*://([^/?#]*)", url or "", re.IGNORECASE)
    return m.group(1).lower() if m else ""


def delivered(har_path=None, har=None, ids=None):
    """Serving impressions an ad response delivered whose request never went out.

    On dziennik.pl the ad server answered the bill_top request with this
    campaign's creative — its Adform impression wrapped in `vu("…")` — but the
    slot sits below the fold and Ad Manager renders it only once it is near
    the viewport. The run waited at the top of the page, the creative never
    rendered, and the report said none of the campaign's tags fired. The
    delivery itself is in the HAR, so the report can say what happened instead.

    Counted only where the browser would request the address once the creative
    renders: inside a script string or call (`vu("…")`, Studio's
    IMPRESSION_IMG, WP's "pixels":[…]) or an attribute (`src=`). That leaves out
    VAST <Impression> text (a video spot that never played — a different
    cause), an address pasted as plain text, which no render would ever
    request (markup_defects names that one), and a <noscript> fallback.

    `ids` limits the search to these ids (the sheet's). ->
    [{"vendor", "id", "slot", "source"}], one per (vendor, id), in HAR order.
    `slot` is the Ad Manager ad unit's last segment, None for other ad servers;
    `source` is the host that answered with the creative.
    """
    har = _load(har_path, har)
    if har is None:
        return []
    ids = {str(i) for i in ids} if ids is not None else None
    entries = har.get("log", {}).get("entries", [])

    requested = set()
    for e in entries:
        for vendor, kind, ident in vendors.classify(e.get("request", {}).get("url", "")):
            if kind == vendors.IMPRESSION and ident:
                requested.add((vendor, ident))

    out, seen = [], set()
    for e in entries:
        req_url = e.get("request", {}).get("url", "") or ""
        # Host and path only: an Ad Manager request carries the auction's
        # targeting (hb_bidder=…) in its query.
        where = req_url.split("?", 1)[0].lower()
        if any(s in where for s in _NOT_A_DELIVERY) or "xml" in _mime(e):
            continue
        text = _body(e)
        if not text or ("track.adform.net" not in text and "ad.doubleclick.net" not in text):
            continue
        readable = _readable(text)
        gam = "/gampad/ads" in req_url
        fallback = [n.span() for n in _NOSCRIPT.finditer(readable)]
        for m in _SERVING_URL.finditer(readable):
            if any(a <= m.start() < b for a, b in fallback):
                continue
            url = m.group(0)
            full = "https:" + url if url.startswith("//") else url
            for vendor, kind, ident in vendors.classify(full):
                if (kind != vendors.IMPRESSION or vendor not in vendors.SERVING_VENDORS
                        or not ident or (ids is not None and ident not in ids)):
                    continue
                key = (vendor, ident)
                if key in seen or key in requested:
                    continue
                # A script string, a call's argument or an attribute value.
                if not m.start() or readable[m.start() - 1] not in "\"'`=":
                    continue
                seen.add(key)
                out.append({"vendor": vendor, "id": ident,
                            "slot": gam_slot(req_url, readable, m.start()) if gam else None,
                            "source": _host(req_url)})
    return out


# ── why did it not happen? ──────────────────────────────────────────────

# What the capture said about itself, turned into a cause. The capture already
# logs the reason a step did not happen; this reads those lines (and one fact
# from the HAR) back out as short statements a person can act on, so a report
# can say "campaign creative never served" instead of leaving "no tag fired"
# to be interpreted.
NOTHING_FIRED = ("none of the sheet's placements fired", "no impression fired")

_EVENT_CAUSES = [
    # Worded as what was observed. "The creative was never served" claimed more
    # than the HAR shows: on an OLX page the Pepco banner was on screen while
    # none of the sheet's placements fired — it carried no tag the sheet books.
    (r"this campaign's impression NOT seen within (\d+)s",
     "none of the sheet's placements fired within {0}s"),
    (r"an impression NOT seen within (\d+)s",
     "no impression fired within {0}s"),
    (r"video impression NOT seen within (\d+)s",
     "the video spot never started within {0}s"),
    (r"page did not finish loading within (\d+)s",
     "the page took longer than {0}s to finish loading"),
    (r"consent wall still up",
     "the consent wall was not dismissed, so nothing served"),
    (r"no overlay appeared in any navigation",
     "the interstitial never appeared on any page visited"),
    (r"click tracked for a DIFFERENT id",
     "the click landed on another advertiser's creative"),
    (r"click skipped: no clickable creative frame found",
     "no clickable creative could be found on the page"),
    (r"click skipped: no player on screen",
     "no player on screen to click"),
    (r"click skipped: creative off-screen",
     "the creative stayed off-screen and could not be reached"),
    (r"model could not locate the creative(?: \(looked through (\d+) screens\))?",
     "the vision check could not find the creative on screen"),
    (r"clicked \(\w+\) but no click beacon followed",
     "the creative was clicked but no click beacon followed"),
    (r"the player consumed the click",
     "the video player took the click instead of the ad"),
    (r"expected creative did not play; a different one did",
     "a different spot played than the one under test"),
]


def bot_challenge(har_path=None, har=None):
    """Did the page answer with a bot-check wall (Cloudflare) rather than
    content? strefabiznesu.pl did, on the reload — and every check after that
    ran against the wall, not the ad."""
    if har is None:
        try:
            with open(har_path, encoding="utf-8") as f:
                har = json.load(f)
        except Exception:
            return False
    for e in har.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        if "/cdn-cgi/challenge-platform/" in url and "orchestrate" in url:
            return True
        if "challenges.cloudflare.com/turnstile" in url:
            return True
    return False


def diagnose(meta, har_path=None, har=None):
    """-> [str]: the identified causes, most basic first.

    Only what the evidence supports; an empty list means the run recorded no
    reason, not that there was none.
    """
    out = []
    if (har_path or har) and bot_challenge(har_path, har):
        out.append("the page served a bot-check wall (Cloudflare) instead of content")
    if meta.get("error"):
        # The run itself stopped; the first line of the exception is the cause.
        out.append("the run stopped with an error: "
                   + str(meta["error"]).splitlines()[0][:100])
    text = [str(e) for e in (meta.get("events") or [])]
    for rx, tpl in _EVENT_CAUSES:
        for line in text:
            m = re.search(rx, line)
            if m:
                msg = tpl.format(*[g or "" for g in m.groups()])
                if msg not in out:
                    out.append(msg)
                break
    # Two ways of saying one thing: the deterministic search found nothing to
    # click and then the vision check found nothing either.
    if "the vision check could not find the creative on screen" in out:
        out = [o for o in out if not o.startswith("no clickable creative could be found")]
    # The creative was never served, so a missing click is a consequence and
    # naming it as a second problem only adds noise.
    if any(o.startswith(NOTHING_FIRED) or "never started" in o for o in out):
        out = [o for o in out if not o.startswith(("no clickable creative", "the vision check",
                                                    "the creative was clicked", "no player on screen"))]
    return out


_URL_IN_BODY = re.compile(r"""https?://[^\s"'<>\\]+""", re.IGNORECASE)

# Ad Manager previews name the creative as creativeId=138620228396; DV360's as
# creativeId=xbid.752653503, and DV360 then fetches that creative from
# …adspreview.googleusercontent.com/preview/…/752653503/previewuser.
_CREATIVE_ID = re.compile(r"[?&]creativeId=(?:xbid\.)?(\d+)")
_PREVIEW_CONTENT = ("adspreview.googleusercontent.com/preview/",
                    "displayads-formats.googleusercontent.com/ads/preview/")


def previewed_creative(url):
    """The creative a preview link shows, or None."""
    m = _CREATIVE_ID.search(url or "")
    return m.group(1) if m else None


def creative_tags(har_path=None, creative_id=None, har=None):
    """The vendor tags carried by the ad response that delivered one creative.

    An Ad Manager or DV360 preview link names the creative it shows
    (`creativeId=`), and the response that served it is in the HAR. Reading
    the tags out of that response answers "what did the creative actually
    carry?" — which separates "the creative never came" from "it came with a
    different placement's tag", two situations that both look like "the
    booked tag did not fire".

    -> sorted [(vendor, kind, id)], serving and measurement vendors alike.
    """
    if not creative_id:
        return []
    har = _load(har_path, har)
    if har is None:
        return []
    found = set()
    cid = str(creative_id)
    for e in har.get("log", {}).get("entries", []):
        url = e.get("request", {}).get("url", "")
        preview = any(p in url for p in _PREVIEW_CONTENT)
        if "gampad/ads" not in url and not preview:
            continue
        text = _body(e)
        # DV360 names the creative in the address it fetches it from, not in it.
        if not text or (cid not in text and not (preview and cid in url)):
            continue
        for url in _URL_IN_BODY.findall(_readable(text)):
            for vendor, kind, ident in vendors.classify(url):
                if ident and ident != "present":
                    found.add((vendor, kind, ident))
    return sorted(found)


def analyze(meta, expected_id=None, require_click=True, rederive=True):
    """Turn one artifact into a verdict.

    expected_id falls back to whatever the artifact was captured against.
    """
    expected_id = expected_id or meta.get("expected_id")

    beacons = meta.get("beacons", [])
    if rederive:
        har = Path(meta.get("_dir", ".")) / meta.get("har", "run.har")
        if har.exists():
            try:
                fired = beacons_from_har(har)
            except Exception:
                # A HAR whose write was cut short is unparsable JSON, and a
                # page that would not stop making requests is exactly when
                # that happens — see _close_context. The recorder saw those
                # beacons live, so fall back to them rather than failing the
                # whole analysis over the copy on disk.
                fired = None
            if fired is not None:
                markup = [b for b in beacons if b.get("evidence") == "in_markup"]
                beacons = fired + markup

    fired = [b for b in beacons if b.get("evidence") == "fired"]
    markup = [b for b in beacons if b.get("evidence") == "in_markup"]

    def match(kind, ident=None, pool=fired):
        return [b for b in pool
                if b["kind"] == kind and (ident is None or b["id"] == ident)]

    imp = match(vendors.IMPRESSION, expected_id)
    clk = match(vendors.CLICK, expected_id)

    # Serving IDs that fired but are not the one under test. On a live page
    # some of these are simply other advertisers. The one that matters is when
    # the expected ID never fired and a different one did in its place —
    # that's the right slot running the wrong tag.
    other_ids = sorted({b["id"] for b in fired
                        if b["vendor"] in vendors.SERVING_VENDORS
                        and b["id"] and b["id"] != expected_id})

    # Impression present only in page source, never requested.
    imp_markup_only = (not imp) and bool(match(vendors.IMPRESSION, expected_id, markup))

    if meta.get("error"):
        verdict = INCONCLUSIVE
    elif not expected_id and imp:
        # No ID to check against, so what fired can be reported but not
        # credited to this campaign.
        verdict = UNATTRIBUTED
    elif imp and (clk or not require_click):
        verdict = PASS
    elif imp:
        verdict = IMPRESSION_ONLY
    elif expected_id and other_ids:
        verdict = WRONG_TAG
    else:
        verdict = MISSING

    measurement = sorted({b["vendor"] for b in fired
                          if b["kind"] == vendors.MEASUREMENT})

    return {
        "id": meta.get("id"),
        "label": meta.get("label"),
        "url": meta.get("url"),
        "expected_id": expected_id,
        "verdict": verdict,
        "impression": imp[0] if imp else None,
        "click": clk[0] if clk else None,
        "impression_in_markup_only": imp_markup_only,
        "other_serving_ids": other_ids,
        "measurement_vendors": measurement,
        "landing": meta.get("landing"),
        "strategy": meta.get("strategy"),
        "viewport": meta.get("viewport"),
        "duration_s": meta.get("duration_s"),
        "error": meta.get("error"),
        "screenshot": meta.get("screenshot"),
        "dir": meta.get("_dir"),
    }


def analyze_run(run_root, expectations=None, require_click=True):
    """Analyze every artifact under a run directory."""
    run_root = Path(run_root)
    out = []
    for d in sorted(p for p in run_root.iterdir() if (p / "meta.json").exists()):
        meta = load_artifact(d)
        exp = (expectations or {}).get(meta.get("id"))
        out.append(analyze(meta, expected_id=exp, require_click=require_click))
    return out


VERDICT_LABEL = {
    PASS: "PASS",
    IMPRESSION_ONLY: "impression only",
    MISSING: "no tag fired",
    WRONG_TAG: "WRONG TAG in slot",
    INCONCLUSIVE: "inconclusive",
    UNATTRIBUTED: "fired, not attributed",
}


def render_table(results):
    w = 104
    lines = ["=" * w,
             f"{'Placement':<30}{'Expected':<12}{'IMP':<6}{'CLK':<6}{'Verdict':<20}{'Note':<28}",
             "-" * w]
    for r in results:
        imp = "✅" if r["impression"] else ("~" if r["impression_in_markup_only"] else "❌")
        clk = "✅" if r["click"] else "❌"
        note = ""
        if r["verdict"] == WRONG_TAG:
            note = "fired instead: " + ", ".join(r["other_serving_ids"][:2])
        elif r["impression_in_markup_only"]:
            note = "in markup, never requested"
        elif r["error"]:
            note = r["error"][:26]
        elif r["measurement_vendors"]:
            note = "+" + ",".join(r["measurement_vendors"])
        lines.append(f"{(r['label'] or '')[:29]:<30}{str(r['expected_id'] or '—'):<12}"
                     f"{imp:<6}{clk:<6}{VERDICT_LABEL[r['verdict']]:<20}{note[:27]:<28}")
    lines.append("=" * w)
    ok = sum(1 for r in results if r["verdict"] == PASS)
    lines.append(f"{ok}/{len(results)} fully verified")
    return "\n".join(lines)
