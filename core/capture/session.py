"""One browser session -> one run artifact.

The split this module exists to enforce: the browser's only job is to produce
evidence. It does not decide anything. Everything it saw goes to disk as a HAR
plus a distilled meta.json, and every verdict is reached later by reading
those files.

That matters practically. Fixing a detection rule used to mean re-running ten
minutes of page loads; now it means re-reading artifacts that are already on
disk. It also makes the evidence sendable — a HAR opens in any browser's
devtools, including the publisher's.
"""

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core import profiles as profiles_mod
from core.analyze import vendors
from core.capture import consent, strategies

URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>()\\]+")


class Recorder:
    """Live beacon log.

    Attached at the CONTEXT level, and to every page the context opens. A
    click tag is fired by the tab the ad opens, not by the page that was
    clicked — a listener bound only to the original page never sees it, which
    is why click verification silently returned nothing before.
    """

    def __init__(self):
        self.t0 = time.time()
        self.beacons = []
        self._seen = set()
        self._pages = set()
        # Frame objects are not JSON-serializable and must not reach
        # meta.json, but the frame that fired an impression is the only
        # reliable handle on which slot the creative is in — so it is kept
        # alongside, keyed the same way.
        self._frames = {}
        # The page waits are made on. See sleep().
        self.page = None

    def bind(self, page):
        """Wait on `page` from now on, so beacons arrive while the run waits."""
        self.page = page

    def sleep(self, seconds):
        """Pause without going deaf.

        Playwright's sync API hands events to Python only while a call into it
        is running. The wait below used to be time.sleep(), so a beacon fired
        during it was delivered — and stamped — only when the wait ended: on
        dziennik.pl the Commercial Break's impression fired at 13s and was
        recorded at 274s, and no wait could ever end on a beacon that arrived
        after it began. Waiting on the bound page dispatches as it goes.
        Unbound, or once the page is gone, this is a plain sleep.
        """
        consent.pause(self.page, seconds)

    def attach(self, ctx):
        ctx.on("request", self._on_request)
        ctx.on("page", self._on_page)
        for p in ctx.pages:
            self._on_page(p)

    def _on_page(self, page):
        if page in self._pages:
            return
        self._pages.add(page)
        try:
            page.on("request", self._on_request)
        except Exception:
            pass

    def _on_request(self, req):
        try:
            url = req.url
        except Exception:
            return
        frame = None
        try:
            frame = req.frame
        except Exception:
            pass
        self.note(url, requested=True, frame=frame)

    def note(self, url, requested, frame=None):
        for vendor, kind, ident in vendors.classify(url):
            key = (vendor, kind, ident, requested)
            if key in self._seen:
                return
            self._seen.add(key)
            if frame is not None:
                self._frames.setdefault((vendor, kind, ident), frame)
            self.beacons.append({
                "t": round(time.time() - self.t0, 1),
                "vendor": vendor,
                "kind": kind,
                "id": ident,
                "url": url,
                # A beacon that was actually requested is proof the tag ran.
                # One only present in markup proves the markup mentions it —
                # frequently because a *different* advertiser's tag is sitting
                # in the same page source. Never let those share a verdict.
                "evidence": "fired" if requested else "in_markup",
            })

    # -- queries used while waiting -------------------------------------
    def has(self, kind=None, ident=None, vendor=None, fired_only=True):
        for b in self.beacons:
            if fired_only and b["evidence"] != "fired":
                continue
            if kind and b["kind"] != kind:
                continue
            if ident and b["id"] != ident:
                continue
            if vendor and b["vendor"] != vendor:
                continue
            return True
        return False

    def wait_for(self, predicate, timeout, poll=0.5):
        """Poll instead of sleeping a fixed block, so a fast page finishes
        fast and a slow one still gets its full budget."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            self.sleep(min(poll, max(0.0, deadline - time.time())))
        # What arrived during the last poll counts too.
        return bool(predicate())

    def serving_ids(self):
        return sorted({b["id"] for b in self.beacons
                       if b["evidence"] == "fired"
                       and b["vendor"] in vendors.SERVING_VENDORS and b["id"]})

    def impression_frame(self, ident=None):
        """The frame that fired an impression — the handle used to locate the
        creative for a click.

        `ident` is one id or a set of them. Only None means "anybody's": with
        a sheet loaded, the first impression of anyone is a competitor's frame
        as often as not (dziennik.pl: a click on the pre-roll's CM360 frame).
        """
        if ident is None or isinstance(ident, str):
            wanted = {ident} if ident else None
        else:
            wanted = {str(i) for i in ident}
        for b in self.beacons:
            if b["kind"] != vendors.IMPRESSION or b["evidence"] != "fired":
                continue
            if wanted is not None and b["id"] not in wanted:
                continue
            fr = self._frames.get((b["vendor"], b["kind"], b["id"]))
            if fr is not None:
                return fr
        return None


def _dom_scan(page, recorder):
    """Record URLs present in markup but never requested, flagged as such."""
    for frame in consent.live_frames(page):
        try:
            html = frame.content()
        except Exception:
            continue
        for m in URL_IN_TEXT.finditer(html):
            recorder.note(m.group(0), requested=False)


def capture(target, browser, out_root, viewport="desktop", overrides=None):
    """Run one test URL and write its artifact.

    target: {"id": str, "url": str, "label": str, "expected_id": str|None}
    Returns the meta dict (also written to meta.json).
    """
    url = target["url"]
    settings = profiles_mod.resolve(url, viewport=viewport, overrides=overrides)

    run_dir = Path(out_root) / target["id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    har_path = run_dir / "run.har"

    vp = settings["viewport"]
    ctx = browser.new_context(
        viewport={"width": vp["width"], "height": vp["height"]},
        user_agent=vp["user_agent"],
        is_mobile=vp.get("is_mobile", False),
        has_touch=vp.get("has_touch", False),
        locale="pl-PL",
        record_har_path=str(har_path),
        # "minimal" leaves out what only replaying a page needs (timings,
        # sizes, cookie detail). It does NOT drop response bodies — a portal's
        # HAR is still 40-60 MB — and the verdict depends on them: what an ad
        # response delivered but never fired (dziennik.pl's bill_top), tags
        # broken in the creative's markup, the previewed creative's own tags.
        # Do not trade them away for size.
        record_har_mode="minimal",
    )

    recorder = Recorder()
    recorder.attach(ctx)
    page = ctx.new_page()
    recorder.bind(page)

    meta = {
        "id": target["id"],
        "label": target.get("label", target["id"]),
        "url": url,
        "expected_id": target.get("expected_id"),
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "viewport": settings["viewport_name"],
        "strategy": settings["strategy"],
        "patience_s": settings["patience"],
        "profiles_applied": settings["profiles_applied"],
        "consent": None,
        "events": [],
        "error": None,
    }

    try:
        drive = strategies.get(settings["strategy"])
        drive(page, ctx, recorder, settings, meta, target)
        _dom_scan(page, recorder)
        try:
            page.screenshot(path=str(run_dir / "final.png"))
            meta["screenshot"] = "final.png"
        except Exception:
            pass
    except Exception as e:
        meta["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        meta["consent"] = meta.get("consent")
        meta["duration_s"] = round(time.time() - recorder.t0, 1)
        meta["beacons"] = recorder.beacons
        meta["har_flush"] = _close_context(ctx)

    meta["har"] = "run.har"
    with open(run_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return meta


def _close_context(ctx):
    """Close the context — which is what writes the HAR.

    Measured on an OLX listing page: `ctx.close()` sat for over twenty
    minutes and the run never reached its second target, because the page
    keeps a long-lived connection open and the HAR will not finalise while
    requests are still in flight. Blanking every page first ends that
    traffic, and that alone fixed it.

    Not done in a worker thread with a timeout, which was the first attempt:
    Playwright's sync API refuses to be driven from another thread
    ("Cannot switch to a different thread"), so every close failed and every
    HAR since was truncated — the tool quietly stopped keeping the evidence
    it exists to keep. A guard that breaks the thing it guards is worse than
    the hang it was written for.
    """
    for page in list(getattr(ctx, "pages", []) or []):
        try:
            page.goto("about:blank", timeout=5000)
        except Exception:
            pass
    try:
        ctx.close()
        return "ok"
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:120]}"


def new_run_dir(root="core/artifacts", campaign="run"):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = Path(root) / f"{stamp}-{campaign}-{uuid.uuid4().hex[:4]}"
    d.mkdir(parents=True, exist_ok=True)
    return d
