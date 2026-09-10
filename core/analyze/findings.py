"""Artifact -> verdict. Pure functions, no browser.

Everything here can run against artifacts captured days ago. That is the point
of the split: when a detection rule turns out to be wrong — and several have
been — the fix is re-running this over stored HARs in a second, not re-driving
twenty publisher pages for ten minutes and hoping the same ads serve again.
"""

import json
from pathlib import Path

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
