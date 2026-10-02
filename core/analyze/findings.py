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


def beacons_from_har(har_path):
    """Re-derive beacons straight from the HAR.

    Independent of whatever the recorder believed at capture time, so a
    corrected vendor pattern applies retroactively to every artifact already
    on disk.
    """
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
_TAG_HOSTS = ("adsafeprotected", "doubleclick.net/ddm", "adform.net",
              "doubleverify", "abtshield")

# <script src=""https://…""> — the attribute value wrapped in a second pair of
# quotes. HTML reads `src=""` as an empty value and the address that follows as
# a stray attribute name, so the element has no source and nothing is requested.
_DOUBLED = re.compile(
    r"<\s*(script|img|iframe)\b[^<>]*?\bsrc\s*=\s*\"\"\s*(https?://[^\"'\s<>]+?)\"\"",
    re.IGNORECASE)


def _readable(text):
    """Undo the layers a creative can arrive in: percent-encoding (DV360's
    preview page hands the markup over as an encoded JS string) and \\xNN
    escapes."""
    bs = chr(92)
    # Any %XX, not just an encoded "<": the markup may arrive with its angle
    # brackets already turned into \x3c first, leaving no %3C to key on.
    if re.search(r"%[0-9A-Fa-f]{2}", text):
        text = unquote(text)
    if bs + "x" in text:
        text = re.sub(re.escape(bs) + r"x([0-9a-fA-F]{2})",
                      lambda m: chr(int(m.group(1), 16)), text)
    return text.replace(bs + "/", "/")


def markup_defects(har_path):
    """Vendor tags present in delivered markup that the browser cannot load.

    The commonest cause, seen twice in two days on different publishers: a tag
    pasted into a creative with CSV-style escaping, so
    `SRC="https://staticjs.adsafeprotected.com/fw.js?…"` arrives as
    `SRC=""https://staticjs.adsafeprotected.com/fw.js?…""`. The script has no
    address, no request is made, and the only symptom is a tag that never fires
    — indistinguishable, from the traffic alone, from one nobody implemented.
    The HAR holds the response bodies, so the cause can be read off directly.

    -> [{"vendor", "kind", "id", "tag", "problem", "url"}], deduplicated.
    Whether the tag *also* fired is the caller's to check against the beacons.
    """
    try:
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)
    except Exception:
        return []

    out, seen = [], set()
    for e in har.get("log", {}).get("entries", []):
        content = e.get("response", {}).get("content", {}) or {}
        mime = (content.get("mimeType") or "").lower()
        if mime.startswith(("image/", "video/", "audio/", "font/")):
            continue
        text = content.get("text") or ""
        if not text:
            continue
        if content.get("encoding") == "base64":
            try:
                text = base64.b64decode(text).decode("utf-8", "replace")
            except Exception:
                continue
        low = text.lower()
        if not any(h in low for h in _TAG_HOSTS):
            continue
        for m in _DOUBLED.finditer(_readable(text)):
            tag, url = m.group(1).lower(), m.group(2)
            for vendor, kind, ident in vendors.classify(url):
                key = (vendor, ident, tag)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "vendor": vendor, "kind": kind, "id": ident, "tag": tag,
                    "url": url[:200],
                    "problem": "the tag is delivered with its attribute wrapped "
                               "in doubled quotes, so its address is empty and "
                               "the browser never requests it",
                })
    return out


# ── why did it not happen? ──────────────────────────────────────────────

# What the capture said about itself, turned into a cause. The capture already
# logs the reason a step did not happen; this reads those lines (and one fact
# from the HAR) back out as short statements a person can act on, so a report
# can say "campaign creative never served" instead of leaving "no tag fired"
# to be interpreted.
_EVENT_CAUSES = [
    (r"(?:this campaign's|an) impression NOT seen within (\d+)s",
     "the campaign's creative was never served within {0}s"),
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
    if any("never served" in o or "never started" in o for o in out):
        out = [o for o in out if not o.startswith(("no clickable creative", "the vision check",
                                                    "the creative was clicked", "no player on screen"))]
    return out


_URL_IN_BODY = re.compile(r"""https?://[^\s"'<>\\]+""", re.IGNORECASE)


def creative_tags(har_path, creative_id):
    """The vendor tags carried by the ad response that delivered one creative.

    An Ad Manager preview link names the creative it shows (`creativeId=`), and
    the response that served it is in the HAR. Reading the tags out of that
    response answers "what did the creative actually carry?" — which separates
    "the creative never came" from "it came with a different placement's tag",
    two situations that both look like "the booked tag did not fire".

    -> sorted [(vendor, kind, id)], serving and measurement vendors alike.
    """
    if not creative_id:
        return []
    try:
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)
    except Exception:
        return []
    found = set()
    cid = str(creative_id)
    for e in har.get("log", {}).get("entries", []):
        if "gampad/ads" not in e.get("request", {}).get("url", ""):
            continue
        content = e.get("response", {}).get("content", {}) or {}
        text = content.get("text") or ""
        if content.get("encoding") == "base64" and text:
            try:
                text = base64.b64decode(text).decode("utf-8", "replace")
            except Exception:
                continue
        if cid not in text:
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
