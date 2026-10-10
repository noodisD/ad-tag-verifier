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

import re
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


def _fired(meta, har=None):
    """Beacons re-derived from the HAR, the same source the verdict uses.

    The recorder's in-memory list misses requests made from a tab the click
    opened — measured on kobieta.wp.pl, where the HAR holds three
    `/C/?bn=89750126` requests that the recorder never saw. Reading the HAR
    here means the table the UI draws and the verdict beside it cannot
    disagree about whether the click fired.

    `har`, when the caller has already parsed it, saves reading it again.
    """
    if har is not None:
        try:
            return findings.beacons_from_har(har=har)
        except Exception:
            pass
    else:
        path = Path(meta.get("_dir", ".")) / meta.get("har", "run.har")
        if path.exists():
            try:
                return findings.beacons_from_har(path)
            except Exception:
                pass
    return [b for b in meta.get("beacons", []) if b.get("evidence") == "fired"]


# Click paths that aimed at the creative under test rather than at whatever
# ad frame was there: the model was asked for this advertiser's creative, and
# "unbooked" clicks the frame of an impression from the sheet's own vendor.
# A frame or link picked for merely being an ad (f8a5/t4 clicked a CM360
# pre-roll's frame on dziennik.pl) says nothing about whose creative it was.
_AIMED = ("model", "unbooked")


def _unbooked_clicks(meta, booked):
    """-> [(source, id, judged_other)]: clicks whose beacon carried an id the
    sheet does not book, in the order made. Two shapes in the log: "click
    tracked for a DIFFERENT id (X)" (judged another advertiser's), whose source
    is the "<source> click at (x,y)" line just before it, and "click confirmed
    by beacon X (source)" for a click aimed at an unbooked id's own frame."""
    out, source = [], None
    for e in meta.get("events", []) or []:
        e = str(e)
        m = re.match(r"(\w+) click at \(", e)
        if m:
            source = m.group(1)
        m = re.search(r"click tracked for a DIFFERENT id \(([^)]+)\)", e)
        if m:
            out.append((source, m.group(1), True))
        m = re.search(r"click confirmed by beacon (\S+) \((\w+)\)", e)
        if m and m.group(1) not in booked:
            out.append((m.group(2), m.group(1), False))
    return out


def _ids(pairs, limit=3):
    return ", ".join(f"{v} {i}" for v, i in pairs[:limit])


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
    # Parsed once and handed to every reader below: a portal's HAR is 40-60 MB.
    har_path = Path(meta.get("_dir", ".")) / meta.get("har", "run.har")
    har = findings.read_har(har_path) if har_path.exists() else None
    fired = _fired(meta, har)

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
    # wrapped in doubled quotes leaves a script with no address; an address
    # pasted as plain text is never requested at all). Without this the page
    # reads as "that tag never fired", which sends the publisher off to look
    # for a tag nobody placed instead of one placed wrongly. Only those that
    # really did not fire are reported — by kind too: on the DV360 previews
    # the click tracker worked while the impression pasted beside it never
    # could, and the same bn on both hid the broken one.
    defects = []
    if har is not None:
        fired_ids = {(b["vendor"], b["kind"], b["id"]) for b in fired}
        defects = [d for d in findings.markup_defects(har=har)
                   if (d["vendor"], d["kind"], d["id"]) not in fired_ids]

    # Why a step did not happen, in words: read from what the capture logged
    # and from the HAR, so the report can name the cause instead of leaving
    # "no tag fired" to be interpreted.
    diagnosis = findings.diagnose(meta, har=har)

    wanted = {str(i) for i in (target.get("wait_for") or []) if i}
    serving_fired = sorted({(b["vendor"], b["id"]) for b in fired
                            if b["vendor"] in vendors.SERVING_VENDORS
                            and b["kind"] == vendors.IMPRESSION and b.get("id")})
    booked_fired = [i for _v, i in serving_fired if i in wanted]
    top = []

    # A broken serving tag is the cause, not a detail: name it first. With a
    # sheet, only the campaign's own ids; anything else on a portal is some
    # other advertiser's problem.
    broken = [d for d in defects
              if d["vendor"] in vendors.SERVING_VENDORS and d["kind"] == vendors.IMPRESSION
              and (not wanted or d["id"] in wanted)]
    for d in broken[:3]:
        top.append(f"{d['vendor']} {d['id']} impression: {d['problem']}")

    # When the sheet's ids are known and none of them fired, say what did.
    # Two very different situations hide behind "the booked tag did not fire":
    # the creative never came, or it came carrying a different placement's tag.
    # A preview link names its creative, so the response that delivered it can
    # be read directly.
    delivered_not_fired, working_unbooked = [], []
    if wanted and not booked_fired and har is not None:
        cid = findings.previewed_creative(target.get("url", ""))
        carried = [(v, i) for v, k, i in findings.creative_tags(creative_id=cid, har=har)
                   if v in vendors.SERVING_VENDORS and k == vendors.IMPRESSION and i not in wanted]
        if carried:
            top.append(f"the previewed creative (creativeId {cid}) carries {_ids(carried)}"
                       ", which the sheet does not book")

        # The campaign's creative reached a slot and was never shown — on
        # dziennik.pl the ad server answered bill_top with it, and Ad Manager
        # renders that slot only near the viewport. "None of the sheet's
        # placements fired" sent people looking for a missing tag.
        broken_ids = {(d["vendor"], d["id"]) for d in defects}
        delivered_not_fired = [d for d in findings.delivered(har=har, ids=wanted)
                               if (d["vendor"], d["id"]) not in broken_ids]
        for d in delivered_not_fired[:3]:
            where = f"to slot {d['slot']}" if d.get("slot") else f"by {d['source']}"
            what = "slot" if d.get("slot") else "creative"
            top.append(f"{d['vendor']} {d['id']} was delivered {where} but its impression "
                       f"never fired — the {what} was not rendered/in view during the test")

        # A click judged "another advertiser's" because the sheet does not
        # book its id, while the same id's impression fired too: the creative
        # works, with a tag the sheet lacks (money.pl's WP previews, Adform
        # 90626723-26). Only for clicks aimed at the creative under test, and
        # never for a genuinely different id — click_confirmed's verdict
        # stands for those.
        clicks = _unbooked_clicks(meta, wanted)
        for source, ident, _other in clicks:
            own = creative_click.own_unbooked(fired, ident, wanted) if source in _AIMED else None
            if own and {"vendor": own[0], "id": own[1]} not in working_unbooked:
                working_unbooked.append({"vendor": own[0], "id": own[1]})
                top.append(f"the creative works — impression and click both carry "
                           f"{own[0]} {own[1]} — but the sheet does not book {own[1]}")
        # The "another advertiser" line goes only when every click judged so
        # is one of these; a click that really did land elsewhere keeps it.
        mine = {w["id"] for w in working_unbooked}
        judged = [i for _s, i, other in clicks if other]
        if judged and all(i in mine for i in judged):
            diagnosis = [d for d in diagnosis
                         if d != "the click landed on another advertiser's creative"]

        others = [p for p in serving_fired
                  if p not in {(w["vendor"], w["id"]) for w in working_unbooked}]
        if others and not carried:
            top.append(("other tags that fired on the page are not in the sheet: "
                        if delivered_not_fired or working_unbooked
                        else "tags fired on the page, but none this campaign books: ")
                       + _ids(others))

    # "None of the sheet's placements fired" is the wait's verdict, reached
    # from what it had seen by then. When the HAR shows a booked impression
    # after all (the vision pass scrolled it into view: dziennik.pl, 90571117
    # at 305s), or something above already explains why none fired, the line
    # contradicts the report it sits in. Without a sheet nothing above is
    # about this campaign — a broken tag on a portal may be anybody's — so
    # "no impression fired" stays.
    if booked_fired or (wanted and top):
        diagnosis = [d for d in diagnosis if not d.startswith(findings.NOTHING_FIRED)]
    diagnosis = top + [d for d in diagnosis if d not in top]

    status = "error" if meta.get("error") else ("done" if found else "none")
    return {
        "status": status,
        "vendors": found,
        "kinds": kinds,
        "markup_defects": defects,
        "diagnosis": diagnosis,
        # Sheet ids an ad response delivered whose impression was never
        # requested: [{vendor, id, slot, source}].
        "delivered_not_fired": delivered_not_fired,
        # Ids the sheet does not book whose impression and click both fired on
        # the creative under test: [{vendor, id}].
        "working_unbooked": working_unbooked,
        "click_attempted": _click_attempted(meta),
        "click_result": meta.get("click_result"),
        "vendors_in_markup": in_markup,
        "detail": meta.get("error") or "",
        "strategy": meta.get("strategy"),
        "duration_s": meta.get("duration_s"),
    }
