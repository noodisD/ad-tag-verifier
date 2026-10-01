"""Bridge between the HTTP API and core/.

The API and its frontend predate core/ and speak a flatter shape, so rather
than change both at once this module translates: core drives the browser and
reaches the verdict, and this maps that onto what the UI already renders.

One rule here is load-bearing:

    The expected ID is derived from the tag URL with the *same* classifier
    that will read the page.

The frontend pulls `dc_trk_aid` out of a CM360 tag, while core keys CM360 off
the number after `B…` — and those are different numbers (the repo's own
fixture has `B36639324.455334468` next to `dc_trk_aid=649061393`). Forwarding
the frontend's value would make every CM360 placement come back "no tag
fired": a confident false negative, which is the exact failure this project
exists to catch. Deriving both sides from one classifier makes the mismatch
unrepresentable.
"""

from pathlib import Path

from core.ai import creative_click, match as ai_match
from core.analyze import findings, vendors
from core.capture import session

# What each vendor's identity is called, for the discover payload the UI reads.
ID_LABEL = {v.name: v.id_label for v in vendors.VENDORS}

# core verdicts -> the five statuses the UI knows how to paint. The nuance
# that gets flattened here is preserved in `verdict` and `detail`.
STATUS = {
    findings.PASS: "pass",
    findings.IMPRESSION_ONLY: "fail",
    findings.MISSING: "fail",
    findings.WRONG_TAG: "fail",
    findings.INCONCLUSIVE: "error",
    findings.UNATTRIBUTED: "fail",
}

DETAIL = {
    findings.PASS: "impression and click both fired",
    findings.IMPRESSION_ONLY: "impression fired, click never did",
    findings.MISSING: "expected tag never fired",
    findings.INCONCLUSIVE: "run did not complete",
    findings.UNATTRIBUTED: "a tag fired, but nothing said which ID to expect — it may belong to another advertiser on the page",
}


def expected_id(target):
    """What to look for on the page, read off the tag URL itself."""
    for _vendor, _kind, ident in vendors.classify(target.get("url", "")):
        if ident:
            return ident
    # Nothing recognisable in the URL — fall back to whatever the caller
    # declared, preferring the serving vendors' identifiers.
    declared = target.get("expected") or {}
    for key in ("bn", "dc_trk_aid", "o", "plc"):
        if declared.get(key):
            return declared[key]
    return None


def _click_attempted(meta):
    """Did the run actually try to click, or did it never get that far?

    "No click beacon" means two completely different things depending on the
    answer. A click that was attempted and produced nothing is a finding. A
    click that was never attempted — the creative sits in no clickable frame,
    or the profile skips it — says nothing at all about the tag, and
    reporting it as a missing click is how correctly implemented placements
    get raised as defects. Watch mode exists for exactly these pages.
    """
    events = meta.get("events", []) or []
    # Any real attempt counts, whichever path made it. A run often tries the
    # overlay first and only then falls through to a path that logs a skip;
    # reading the skip and ignoring the attempt reported a click that did
    # happen — and landed — as never tested.
    # A click the ad never received is not an attempt in the sense that
    # matters here: the question is whether the tag was tested, and it was
    # not. Some players take the click as play/pause and the SDK never sees
    # it — reporting that as "clicked, nothing tracked" accuses the tag.
    if meta.get("click_result") == "not_testable":
        return False
    # Every path that actually clicks logs "<source> click at (x,y)" — element,
    # overlay, model, video. Listing the sources by hand meant a new strategy
    # silently reported its clicks as never attempted: the video runs came back
    # with a confirmed beacon next to "click not confirmed". The frame path
    # used to word its own line differently ("click element at"), which is why
    # the shape is now uniform rather than the matcher being made cleverer.
    if any("click at (" in e for e in events):
        return True
    if any("click skipped" in e or "link click failed" in e for e in events):
        return False
    return None      # nothing logged either way


def _fired(meta):
    """Beacons re-derived from the HAR, the same source the verdict uses.

    The recorder's in-memory list misses requests made from a tab the click
    opened — measured on kobieta.wp.pl, where the HAR holds three
    `/C/?bn=89750126` requests that the recorder never saw. Reading the HAR
    here means the table the UI draws and the verdict beside it cannot
    disagree about whether the click fired.
    """
    har = Path(meta.get("_dir", ".")) / meta.get("har", "run.har")
    if har.exists():
        try:
            return findings.beacons_from_har(har)
        except Exception:
            pass
    return [b for b in meta.get("beacons", []) if b.get("evidence") == "fired"]


def _group(beacons, key):
    out = {}
    for b in beacons:
        bucket = out.setdefault(key(b), [])
        if b.get("id") and b["id"] not in bucket:
            bucket.append(b["id"])
    return out


def _run(target, browser, run_dir):
    """Capture one target and hand back (meta_with_dir, artifact_dir)."""
    job = {
        "id": target["id"],
        "url": target["url"],
        "label": target.get("label", target["id"]),
        "expected_id": expected_id(target),
        # The campaign's own ids, when the UI has a sheet. Only tells the
        # capture when it may stop waiting; everything that fires is still
        # recorded, and the verdict is still reached from the HAR.
        "wait_for": [str(i) for i in (target.get("wait_for") or []) if i][:500],
    }
    # `overrides` is how the HTTP layer reaches into a run already in flight:
    # it carries the watch-mode stop signal, and silences the console
    # narration the CLI prints, which has no reader when this is driven over
    # the API.
    overrides = dict(target.get("overrides") or {})
    # Who the campaign belongs to. Without it the vision fallback has no way
    # to tell this campaign's creative from the three others on the page, so
    # it is not offered a guess — it is simply not asked.
    if target.get("advertiser"):
        overrides["advertiser"] = target["advertiser"]
        eye = creative_click.VisionMatcher(ai_match.default_model())
        if eye.available:
            overrides["vision"] = eye

    session.capture(job, browser, run_dir,
                    viewport=target.get("viewport", "desktop"),
                    overrides=overrides)
    art = Path(run_dir) / target["id"]
    return findings.load_artifact(art), art


def verify(browser, target, run_dir):
    """-> the /verify result shape for one target."""
    meta, _ = _run(target, browser, run_dir)
    exp = expected_id(target)
    r = findings.analyze(meta, expected_id=exp)

    detail = DETAIL.get(r["verdict"], "")
    if r["verdict"] == findings.WRONG_TAG:
        detail = ("expected tag never fired; these served instead: "
                  + ", ".join(r["other_serving_ids"][:4]))
    elif r["impression_in_markup_only"]:
        detail = "found in page source but never requested — not an impression"
    if r["error"]:
        detail = r["error"]

    return {
        "status": STATUS.get(r["verdict"], "error"),
        "verdict": r["verdict"],
        "observed": _group(_fired(meta), lambda b: f"{b['vendor']} {b['kind']}"),
        "expected": {"id": exp} if exp else {},
        "detail": detail,
        "click_attempted": _click_attempted(meta),
        "click_result": meta.get("click_result"),
        "strategy": meta.get("strategy"),
        "duration_s": meta.get("duration_s"),
        "landing": meta.get("landing"),
    }


def discover(browser, target, run_dir):
    """-> the /discover result shape for one target."""
    meta, _ = _run(target, browser, run_dir)
    fired = _fired(meta)

    found = {}
    for b in fired:
        label = ID_LABEL.get(b["vendor"], "id")
        bucket = found.setdefault(b["vendor"], {}).setdefault(label, [])
        if b.get("id") and b["id"] not in bucket:
            bucket.append(b["id"])

    # The same beacons, split by what they are. `found` collapses impression
    # and click into one bucket per vendor, which cannot answer the question
    # this tool is for — "does the click track too?". The classifier already
    # knows the kind; dropping it here made a click-less placement look
    # identical to a fully working one.
    kinds = {}
    for b in fired:
        bucket = kinds.setdefault(b["vendor"], {}).setdefault(b["kind"], [])
        if b.get("id") and b["id"] not in bucket:
            bucket.append(b["id"])

    # Present in the markup but never requested. Kept apart on purpose: on a
    # live page that markup is frequently a different advertiser's, and
    # counting it as "found" is how a missing tag comes to look fine.
    markup = [b for b in meta.get("beacons", []) if b.get("evidence") == "in_markup"]
    in_markup = {}
    for b in markup:
        if b["vendor"] in found and b.get("id") in found[b["vendor"]].get(
                ID_LABEL.get(b["vendor"], "id"), []):
            continue
        label = ID_LABEL.get(b["vendor"], "id")
        bucket = in_markup.setdefault(b["vendor"], {}).setdefault(label, [])
        if b.get("id") and b["id"] not in bucket:
            bucket.append(b["id"])

    # Tags the creative delivered but the browser could not load (an attribute
    # wrapped in doubled quotes leaves a script with no address). Without this
    # the page reads as "that tag never fired", which sends the publisher off to
    # look for a tag nobody placed instead of one placed wrongly. Only those
    # that really did not fire are reported.
    defects = []
    har = Path(meta.get("_dir", ".")) / meta.get("har", "run.har")
    if har.exists():
        fired_ids = {(b["vendor"], b["id"]) for b in fired}
        defects = [d for d in findings.markup_defects(har)
                   if (d["vendor"], d["id"]) not in fired_ids]

    status = "error" if meta.get("error") else ("done" if found else "none")
    return {
        "status": status,
        "vendors": found,
        "kinds": kinds,
        "markup_defects": defects,
        "click_attempted": _click_attempted(meta),
        "click_result": meta.get("click_result"),
        "vendors_in_markup": in_markup,
        "detail": meta.get("error") or "",
        "strategy": meta.get("strategy"),
        "duration_s": meta.get("duration_s"),
    }
