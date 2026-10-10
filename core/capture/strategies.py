"""How to drive a page, per site shape.

Four strategies, chosen by profile. Each one takes the same arguments and
records what it did into `meta["events"]`, so the artifact says not just what
fired but what the tool did to make it fire.
"""

import re
import time
import uuid
from urllib.parse import unquote

from core.ai import creative_click
from core.capture import consent
from core.analyze import vendors


def get(name):
    try:
        return _STRATEGIES[name]
    except KeyError:
        raise ValueError(f"unknown strategy: {name}")


def _log(meta, msg):
    meta["events"].append(msg)


def _goto(page, url, meta, timeout=60000):
    """Navigate, and carry on if the load event is late.

    A heavy portal can take longer than a minute to fire `load` while every ad
    on it has long since been requested. Raising there threw away the run:
    on kobieta.gazeta.pl one of six identical Pepco tests came back as
    "TimeoutError: Page.goto" with no result at all, although the page was up
    and the HAR was recording. Whatever has loaded is evidence; the wait that
    follows decides whether it is enough. Only a timeout is tolerated — a
    refused connection or a bad certificate still raises.
    """
    try:
        page.goto(url, wait_until="load", timeout=timeout)
    except Exception as e:
        if type(e).__name__ != "TimeoutError":
            raise
        _log(meta, f"page did not finish loading within {timeout // 1000}s — "
                   "carrying on with what has loaded")


def _pause(page, seconds):
    """Wait while the page keeps reporting what it requests — never time.sleep
    on a path where a beacon may arrive (see consent.pause)."""
    consent.pause(page, seconds)


def _deadline(recorder, settings):
    """When the strategy has to hand the page back, as a time.time() value.

    The backend kills a target's browser 420s after it starts, and a killed
    run loses its verdict and possibly its HAR. `run_budget` sits under that
    with room left for the DOM scan, the screenshot and writing the HAR, and
    every optional step after the wait — the vision search, a second click,
    going back after a stray navigation — is measured against it.
    """
    t0 = getattr(recorder, "t0", None)
    return None if t0 is None else t0 + settings.get("run_budget", 380)


def _left(deadline):
    return float("inf") if deadline is None else deadline - time.time()


def _scroll(page, settings):
    """Lazy-loaded slots need the viewport to move past them.

    Always ends back at the top. It used to return from the middle of the
    loop when a scroll call failed, leaving the run parked wherever that was.
    """
    for i in range(settings.get("scroll_passes", 6)):
        try:
            page.evaluate("(y) => window.scrollBy(0, y)", settings.get("scroll_step", 500))
        except Exception:
            break
        _pause(page, 0.8)
    try:
        page.evaluate("() => window.scrollTo(0, 0)")
    except Exception:
        pass


def _wait_for_impression(recorder, settings, meta, expected_id=None, wait_for=None,
                         page=None):
    """Poll for the campaign's impression beacon.

    Waiting long enough is the single most consequential setting here. A
    publisher whose stack takes 90s looks identical to one with no tag
    implemented if the budget is 10s, and the second reading is the one that
    gets reported to the publisher as a fault.

    `wait_for` is a set of ids — the campaign's own, from the trafficking
    sheet — used only to decide when to stop waiting, never what to record.
    Without it a scan stops at the first impression of *anyone*, and on
    dziennik.pl the campaign's creative only arrives on a slot refresh 132s
    after load: a foreign tag at 20s would end the run before ours had a
    chance to appear.

    With a `page` (and `patrol`, on by default) the wait walks the page
    instead of sitting at the top of it — see _patrol.

    The patience is cut short when waiting all of it would leave the click no
    time inside the run's budget (see _deadline): a page slow to load on
    dziennik.pl (260s patience) could otherwise reach the backend's 420s kill
    mid-click and lose the verdict along with it.
    """
    ids = {str(i) for i in (wait_for or []) if i}

    def seen():
        if expected_id:
            return recorder.has(kind=vendors.IMPRESSION, ident=expected_id)
        if ids:
            return any(recorder.has(kind=vendors.IMPRESSION, ident=i) for i in ids)
        return recorder.has(kind=vendors.IMPRESSION)

    patience = settings["patience"]
    room = _left(_deadline(recorder, settings)) - AFTER_WAIT_S
    if room < patience:
        patience = max(int(room), min(patience, MIN_WAIT_S))
        _log(meta, f"the page took long to come up — waiting {patience}s, not "
                   f"{settings['patience']}s, to leave the click time within the run's budget")
        settings = dict(settings, patience=patience)
    if page is not None and settings.get("patrol", True):
        ok = _patrol(page, recorder, settings, meta, seen)
    else:
        ok = recorder.wait_for(seen, patience, settings.get("poll_interval", 0.5))
    what = ("this campaign's impression" if (expected_id or ids) else "an impression")
    _log(meta, f"{what} {'seen' if ok else 'NOT seen'} within {patience}s"
               + (f" (waited for {len(ids)} sheet ids)" if ids and not expected_id else ""))
    return ok


# What the steps after the wait need inside the run's budget: a frame click
# and its confirmation (~30s), or the vision search screen by screen.
AFTER_WAIT_S = 60
# Never cut the wait itself below this.
MIN_WAIT_S = 10


# What the patrol needs to know, in one call: how far the page scrolls, how
# tall a screen is, and where the ad frames are (page y and height of every
# visible iframe over 50x50). Measured on the frame, not on the slot around
# it: dziennik.pl's bill_top div measures 1176x0 while the creative's
# google_ads_iframe inside it is 1140x600.
_PAGE_SHAPE = """() => {
    const se = document.scrollingElement || document.documentElement;
    const ads = [];
    for (const f of document.querySelectorAll('iframe')) {
        const r = f.getBoundingClientRect();
        if (r.width <= 50 || r.height <= 50) continue;
        const st = getComputedStyle(f);
        // A fixed frame is on screen wherever the page is; nothing to walk to.
        if (st.display === 'none' || st.visibility === 'hidden' || st.position === 'fixed') continue;
        ads.push([Math.round(r.top + scrollY), Math.round(r.height)]);
    }
    return {height: se.scrollHeight, view: innerHeight, ads: ads.slice(0, 40)};
}"""

# Scroll, and say where the page actually went: a page an interstitial has
# locked (overflow:hidden on the body) stays put.
_SCROLL_TO = """(y) => {
    window.scrollTo({top: y, left: 0, behavior: 'instant'});
    return Math.round(window.scrollY);
}"""


def _patrol_stops(height, view, ads, screens):
    """Where the patrol holds the page, top first. -> sorted scroll offsets.

    Screens of 0.85 of the viewport — the step the vision search uses too —
    down to the bottom (H-V is always a stop, or a slot in the last screen is
    never shown), but no deeper than `screens` of them: a listing that loads
    more as it is scrolled has no bottom. An ad frame no screen shows whole
    gets a stop of its own, centred on it.
    """
    view = max(int(view or 0), 200)
    step = max(int(view * 0.85), 200)
    bottom = max(int(height or 0) - view, 0)
    reach = min(bottom, step * max(int(screens) - 1, 0))
    stops = list(range(0, reach + 1, step))
    if stops[-1] < reach:
        stops.append(reach)
    for top, h in ads:
        if top + h <= 0 or top >= reach + view:
            continue                           # beyond where the patrol goes
        if any(s <= top and top + h <= s + view for s in stops):
            continue                           # some screen already shows it whole
        stops.append(int(min(max(top + h / 2 - view / 2, 0), reach)))
    out = []
    for y in sorted(stops):
        if not out or y - out[-1] > 40:
            out.append(y)
    return out


def _patrol(page, recorder, settings, meta, seen):
    """Wait for the impression while walking the page, not parked at its top.

    Measured on dziennik.pl: GPT renders a slot below the fold only once it is
    near the viewport, and the creative's impression is a call made on render.
    Ad Manager had already returned the campaign's 1140x600 for bill_top at
    y=1234; the run then waited 260s at the top of a 900px window and reported
    the tag as not firing. Scrolled to, it fired within a second.

    So the wait goes down the page a screen at a time, holding each screen
    `patrol_dwell` seconds and stopping on any ad frame no screen shows whole,
    then starts again from the top with the page measured afresh — it grows
    as slots fill — until the campaign's impression fires or the patience runs
    out. It stays where the impression fired, so the click finds the creative
    on screen; otherwise it goes back to the top.
    """
    patience = settings["patience"]
    poll = settings.get("poll_interval", 0.5)
    dwell = max(settings.get("patrol_dwell", 2), 0.5)
    screens = settings.get("patrol_screens", 12)
    started = time.time()
    deadline = started + patience
    if seen():
        return True
    passes = held = stuck = 0
    where, fired_at = 0, None
    while fired_at is None and time.time() < deadline:
        try:
            shape = page.evaluate(_PAGE_SHAPE)
        except Exception:
            shape = None                       # mid-navigation; look again shortly
        if not shape:
            if recorder.wait_for(seen, min(dwell, max(0.0, deadline - time.time())), poll):
                fired_at = where
            continue
        passes += 1
        for y in _patrol_stops(shape.get("height"), shape.get("view"),
                               shape.get("ads") or [], screens):
            left = deadline - time.time()
            if left <= 0:
                break
            try:
                at = page.evaluate(_SCROLL_TO, y)
            except Exception:
                at = None
            where = y if at is None else at
            if y and at is not None and abs(at - y) > 50:
                stuck += 1
            held += 1
            if recorder.wait_for(seen, min(dwell, left), poll):
                fired_at = where
                break
    if fired_at is None and seen():            # arrived during the last scroll
        fired_at = where

    took = time.time() - started
    meta["patrol"] = {"passes": passes, "stops": held, "fired_at_y": fired_at,
                      "stuck": stuck, "s": round(took, 1)}
    note = (f"; the page would not scroll at {stuck} of them (something holding it)"
            if stuck else "")
    if fired_at is not None:
        _log(meta, f"patrol: fired with the page at y={fired_at} — pass {passes}, "
                   f"{held} stops, {took:.0f}s into the wait{note}")
        return True
    try:
        page.evaluate("() => window.scrollTo(0, 0)")
    except Exception:
        pass
    _log(meta, f"patrol: {passes} passes over the page, {held} stops of {dwell:g}s, "
               f"nothing fired — back at the top{note}")
    return False


# ── click verification ────────────────────────────────────────────────────

def _creative_frame(recorder, page, expected_id=None):
    """The frame that fired the impression, walked up to something clickable.

    Identifying the creative by iframe size or by searching frame HTML for the
    campaign ID both misfire on pages carrying several same-size slots — the
    ID is an 8-digit string that collides with cache-busters and consent
    strings, and size matches the competitor's slot just as well. The frame
    that actually sent the beacon is the only unambiguous answer.

    Even so this is best-effort: the pixel's own frame is often a 0x0 tracker,
    and the slot can be refreshed with a different advertiser between the
    impression and the click. Where that matters, use the watch strategy.

    With an `expected_id` the click-through links below are held to it: one
    carrying another id is never taken (see _href_is_ours).
    """
    ids = [str(expected_id)] if expected_id else None
    target_frame = recorder.impression_frame(expected_id)
    if target_frame is None:
        # No impression means no evidence of which frame is ours. Falling back
        # to "the first frame over 50x50" reads as a reasonable guess and is
        # not one: measured on wiadomosci.wp.pl it picked a competitor's
        # creative and followed it to admaster.cc. On a page full of ad frames
        # that guess is wrong more often than right, so make none — the
        # identity-based paths below still apply, and only to links that say
        # they are ours.
        return _clickthrough_element(page, ids=ids)

    el, box = _frame_box(target_frame)
    if box:
        return el, box

    # No iframe to click. That is not a failure — plenty of creatives render
    # as an element in the main document (static banners, screening
    # wallpapers), and the frame that fired their pixel is the page itself,
    # which has no frame element to walk up to.
    #
    # Fall back to the click-through link. Matching on the click tracker in
    # the href identifies the creative outright, so unlike a size or position
    # guess it cannot land on a competitor's ad sitting in the same page.
    # The creative is known to be here, so a link with no readable id is
    # still a candidate (clickonometrics' previews: the CM360 pixel fires from
    # the page itself and the link only reaches CM360 by redirect).
    return _clickthrough_element(page, ids=ids, strict=False)


def _frame_box(frame):
    """A frame walked up to the first element of it big enough to be a
    creative. -> (element, box), or (None, None)."""
    cur = frame
    while cur is not None:
        try:
            el = cur.frame_element()
            box = el.bounding_box()
        except Exception:
            box = None
        if box and box["width"] >= 50 and box["height"] >= 50:
            return el, box
        cur = getattr(cur, "parent_frame", None)
    return None, None


CLICK_HREF_HINTS = ("track.adform.net/C/", "adclick.g.doubleclick.net",
                    "ad.doubleclick.net/ddm/trackclk", "/ddm/clk",
                    # clickonometrics' own preview serves the banner as a plain
                    # <img> inside <a href=".../click/<bn>/previewclick.html">,
                    # in the main document, with no iframe at all.
                    "clickonometrics.pl/campaign=")

# Click redirectors whose link carries no id a vendor rule can read — the
# tracker's id only appears after the server's redirect. clickonometrics'
# preview links go .../campaign=52980/click/508323/previewclick.html and 302
# to CM360's trackclk; 24 confirmed BNP clicks came through that link.
CLICK_REDIRECTORS = (re.compile(r"clickonometrics\.pl/campaign=[^/]+/click/"),)


def _decoded(href):
    """A link with its percent-encoding peeled off, however many layers deep.
    Ad Manager hands the tracker over inside `adurl=`, encoded once or twice."""
    text = href or ""
    for _ in range(3):
        nxt = unquote(text)
        if nxt == text:
            break
        text = nxt
    return text


def _href_is_ours(href, ids, strict=True):
    """May a click-through link be clicked as one of `ids`' creative?

    Yes when it carries one of them. No when it carries an id that is not one
    of them — that is another placement's or advertiser's link, whatever the
    host. A link with no readable id is taken only from a known redirector:
    `adclick.g.doubleclick.net` alone is on every Ad Manager ad on a page, and
    picking one of those when none of ours had fired is how the dziennik.pl
    runs clicked their way into the site's own WIADOMOŚCI section.

    `strict=False` is for when the creative is known to be on the page — its
    impression fired from the page itself, so there is no frame to aim at —
    and a link with no readable id is taken as it always was. One carrying
    somebody else's id still is not.
    """
    text = _decoded(href)
    carried = {str(ident) for vendor, _kind, ident in vendors.classify(text)
               if ident and vendor in vendors.SERVING_VENDORS}
    if carried:
        return bool(carried & {str(i) for i in ids})
    # Ids in shapes no vendor rule reads (CM360's /ddm/clk/<ad>;<placement>;…).
    # Bounded by non-alphanumerics, so a digit run inside a token is not one.
    for ident in ids:
        if re.search(r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(str(ident)), text):
            return True
    return not strict or any(rx.search(text) for rx in CLICK_REDIRECTORS)


# Every link matching a hint, with the largest visible piece of it — the
# anchor is not always the thing with a size: a link wrapping a block-level
# <img> can measure 160x17 while the 160x600 banner inside it is what a person
# clicks. Largest first.
_CLICKTHROUGH_CANDIDATES = """(hints) => {
    const out = [];
    for (const a of document.querySelectorAll('a[href]')) {
        if (!hints.some(h => a.href.includes(h))) continue;
        let best = null, bestArea = 0;
        const parts = [a].concat(Array.from(
            a.querySelectorAll('img, picture, canvas, video, svg')));
        for (const e of parts) {
            const r = e.getBoundingClientRect();
            const area = r.width * r.height;
            if (r.width >= 30 && r.height >= 20 && area > bestArea) {
                best = e; bestArea = area;
            }
        }
        if (best) out.push({el: best, href: a.href, area: bestArea});
    }
    out.sort((p, q) => q.area - p.area);
    return out;
}"""


def _clickthrough_element(page, ids=None, strict=True):
    """An <a> whose href is the campaign's click tracker, in any frame.

    `ids`, when given, are the only ids whose link may be taken (see
    _href_is_ours, which `strict` is passed on to). Without them — no sheet —
    any link to a click tracker does, as it always did.
    """
    for fr in consent.live_frames(page):
        try:
            cands = fr.evaluate_handle(_CLICKTHROUGH_CANDIDATES, list(CLICK_HREF_HINTS))
            hrefs = cands.evaluate("cs => cs.map(c => c.href)") or []
            for i, href in enumerate(hrefs):
                if ids is not None and not _href_is_ours(href, ids, strict):
                    continue
                el = cands.evaluate_handle("(cs, i) => cs[i].el", i).as_element()
                if not el:
                    continue
                box = el.bounding_box()
                if box and box["width"] >= 30 and box["height"] >= 20:
                    return el, box
        except Exception:
            continue
    return None, None


# What an interstitial looks like from the page's own point of view: a big
# element, lifted above the article, that was not there a moment ago.
_OVERLAY_PROBE = """() => {
  const vw = innerWidth, vh = innerHeight;
  let best = null;
  for (const el of document.querySelectorAll('div,iframe,img,a,section,aside')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || +st.opacity === 0) continue;
    const pos = st.position;
    if (pos !== 'fixed' && pos !== 'absolute' && pos !== 'sticky') continue;
    const z = parseInt(st.zIndex, 10);
    if (!(z > 100)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < vw * 0.4 || r.height < vh * 0.3) continue;
    if (r.bottom < 0 || r.top > vh) continue;
    const area = r.width * r.height;
    if (!best || area > best.area)
      best = {area, x: r.left + r.width / 2, y: r.top + r.height / 2,
              w: Math.round(r.width), h: Math.round(r.height),
              tag: el.tagName, z};
  }
  return best;
}"""


def _await_overlay(page, timeout, poll=0.15):
    """Poll the DOM for an interstitial and return it the moment it appears.

    Waiting for the impression beacon and only then looking was the wrong
    order: a Commercial Break is shown *during* the transition and is gone by
    the time the beacon has been seen and reacted to — measured on
    kobieta.wp.pl, where the element under the cursor turned out to be the
    article's own hero image. Watching the page instead catches it while it is
    up, which is the only moment it can be clicked.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            found = page.evaluate(_OVERLAY_PROBE)
        except Exception:
            found = None            # mid-navigation; try again
        if found:
            return found
        _pause(page, poll)
    return None


_OVERLAY_LINK_PROBE = """() => {
    const e = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
    const a = e && e.closest && e.closest('a[href]');
    if (!a) return null;
    const r = a.getBoundingClientRect();
    if (r.width * r.height < 0.3 * innerWidth * innerHeight) return null;
    return [innerWidth / 2, innerHeight / 2];
}"""


def _wait_overlay_link(page, timeout, poll=0.2):
    """-> (x, y) of the centre once a link that fills the screen sits there, else None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pt = page.evaluate(_OVERLAY_LINK_PROBE)
        except Exception:
            pt = None
        if pt:
            return tuple(pt)
        _pause(page, poll)
    return None


# A layer over the whole page that is not the creative under test. On
# dziennik.pl desktop the pop-up slot shows another advertiser's interstitial
# — position fixed, 100vw x 100vh, z-index 2147483647 — from about 16s to
# 34s, and closes itself. Looked for in the stack under the centre of the
# screen, where anything covering the page sits; a layer that lets clicks
# through (pointer-events:none) is not in that stack and is no obstacle.
_COVER_PROBE = """() => {
    const vw = innerWidth, vh = innerHeight;
    for (const el of document.elementsFromPoint(vw / 2, vh / 2)) {
        const st = getComputedStyle(el);
        if (st.position !== 'fixed' || st.visibility === 'hidden') continue;
        if (!(parseInt(st.zIndex, 10) >= 100000)) continue;
        const r = el.getBoundingClientRect();
        if (r.width >= vw * 0.9 && r.height >= vh * 0.9) return el;
    }
    return null;
}"""

# How long a creative click waits for somebody else's interstitial to close.
# The one on dziennik.pl closes itself after 15s.
FOREIGN_LAYER_WAIT_S = 20

# The least a click needs of the run's budget: the click itself, a tab
# opening, and the confirmation wait (8s) after it.
CLICK_NEEDS_S = 20


def _top_element(el):
    """The element of the main document holding `el`: itself, or the iframe
    its frame sits in, walked up to the top."""
    try:
        fr = el.owner_frame()
        while fr is not None and fr.parent_frame is not None:
            el = fr.frame_element()
            fr = fr.parent_frame
        return el
    except Exception:
        return None


def _foreign_layer(page, mine=None):
    """A full-screen layer over the page that does not hold `mine` (the
    creative's element, when one is known). -> a short description, or None."""
    try:
        layer = page.evaluate_handle(_COVER_PROBE).as_element()
        if layer is None:
            return None
        top = _top_element(mine) if mine is not None else None
        if top is not None and layer.evaluate(
                "(l, e) => l === e || l.contains(e) || e.contains(l)", top):
            return None              # it is the creative under test, or holds it
        return layer.evaluate(
            """l => { const r = l.getBoundingClientRect();
                      return '<' + l.tagName.toLowerCase() + (l.id ? '#' + l.id.slice(0, 40) : '')
                             + '> ' + Math.round(r.width) + 'x' + Math.round(r.height)
                             + ' z=' + getComputedStyle(l).zIndex; }""")
    except Exception:
        return None


def _wait_out_layer(page, settings, meta, mine=None, deadline=None):
    """Before a creative click, give somebody else's full-screen layer time to
    close. -> True when nothing covers the page (any more).

    A click made through it lands on the layer — another advertiser's
    interstitial — and is reported as that advertiser's, or is refused. This
    matters more now that the run sees its impression the moment it fires: on
    dziennik.pl the click moved from 275s, long after the interstitial had
    gone, into the 15 seconds it is up. A layer that holds `mine` is the
    creative under test (an interstitial the sheet books), not an obstacle.
    """
    what = _foreign_layer(page, mine)
    if not what:
        return True
    spent = meta.get("foreign_layer_wait_s", 0)
    limit = min(FOREIGN_LAYER_WAIT_S - spent, _left(deadline) - 60)
    if limit < 1:
        _log(meta, f"a full-screen layer that is not ours covers the page ({what}); "
                   "no time left to wait for it")
        return False
    _log(meta, f"a full-screen layer that is not ours covers the page ({what}) — "
               f"waiting up to {limit:.0f}s for it to close")
    t = time.time()
    gone = False
    while time.time() - t < limit:
        _pause(page, 0.5)
        if not _foreign_layer(page, mine):
            gone = True
            break
    took = time.time() - t
    meta["foreign_layer_wait_s"] = round(spent + took, 1)
    _log(meta, f"    it closed after {took:.0f}s" if gone
               else f"    still up after {took:.0f}s — going ahead")
    return gone


def _same_page(a, b):
    def bare(u):
        return (u or "").split("#", 1)[0].rstrip("/")
    return bare(a) == bare(b)


class _TabWatch:
    """Did a click send the test tab itself to another page?

    Only a new tab was ever watched for, so a click that navigated the tab it
    was made in went unnoticed: on dziennik.pl the run then searched for the
    creative, scanned the DOM and took its screenshot on the site's
    WIADOMOŚCI section. A changed URL is not the test — players and
    infinite articles rewrite theirs with pushState while staying put — so
    the document is marked before the click, and only a main-frame
    navigation that leaves a document without the mark counts.

    The event handlers make no Playwright calls: the sync API would be
    re-entered from inside its own dispatch.
    """

    def __init__(self, page):
        self.page = page
        self.navigated = []
        self.requested = False
        self.token = uuid.uuid4().hex
        try:
            self.before = page.url
        except Exception:
            self.before = ""
        try:
            page.evaluate("(t) => { window.__atvDoc = t; }", self.token)
            self.marked = True
        except Exception:
            self.marked = False
        try:
            page.on("framenavigated", self._on_navigated)
            page.on("request", self._on_request)
            self.listening = True
        except Exception:
            self.listening = False

    def _on_navigated(self, frame):
        try:
            if frame.parent_frame is None:
                self.navigated.append(frame.url)
        except Exception:
            pass

    def _on_request(self, req):
        try:
            if req.is_navigation_request() and req.frame.parent_frame is None:
                self.requested = True
        except Exception:
            pass

    def left(self, settle=5):
        """-> the URL the tab was taken to, or None if it is still on the
        document it was on before the click."""
        if self.requested and not self.navigated:
            # Asked for and not committed yet: give it a moment to land.
            t = time.time()
            while not self.navigated and time.time() - t < settle:
                _pause(self.page, 0.25)
        if not self.navigated:
            return None
        mark = None
        for _ in range(8):
            try:
                mark = self.page.evaluate("() => window.__atvDoc || null")
                break
            except Exception:
                _pause(self.page, 0.5)          # mid-navigation; ask again
        if self.marked and mark == self.token:
            return None                         # same document: pushState, #hash
        try:
            now = self.page.url
        except Exception:
            return None
        if _same_page(now, self.before):
            return None                         # reloaded in place, not gone anywhere
        return now

    def stop(self):
        if not self.listening:
            return
        for event, fn in (("framenavigated", self._on_navigated),
                          ("request", self._on_request)):
            try:
                self.page.remove_listener(event, fn)
            except Exception:
                pass


def _back_to_test_page(page, recorder, settings, meta, watch):
    """Undo a click that navigated the test tab itself: go back, once.

    Everything after the click — the vision search, the DOM scan, the final
    screenshot — is about the test page, so it has to be the test page. A
    click-through that opens in the same tab is still a click-through: the
    beacon has already judged it, and its landing is kept. Only the time the
    run has left is spent on going back, never a fresh page load: the backend
    kills a target at 420s and the result goes with it.
    """
    try:
        to = watch.left()
    finally:
        watch.stop()
    if not to:
        return
    ours = meta.get("click_result") == "confirmed"
    if ours and not meta.get("landing"):
        meta["landing"] = to
    left = _left(_deadline(recorder, settings)) - 10
    back = False
    if left >= 5:
        try:
            page.go_back(wait_until="domcontentloaded", timeout=int(min(15, left) * 1000))
        except Exception:
            pass
        try:
            back = _same_page(page.url, watch.before)
        except Exception:
            back = False
    t0 = getattr(recorder, "t0", None)
    meta["navigated_away"] = {"t": round(time.time() - t0, 1) if t0 else None,
                              "url": to[:300], "returned": back}
    what = ("the click-through opened in the test tab itself" if ours
            else "the click took the test tab itself away")
    if back:
        _log(meta, f"{what} ({to[:120]}) — went back to the test page")
        _pause(page, 2)
    else:
        _log(meta, f"{what} ({to[:120]}) — could not go back"
                   + (" in the time left" if left < 5 else f"; now on {page.url[:100]}"))


def _click_overlay(page, ctx, recorder, settings, meta, expected_id):
    """Click a full-screen overlay, straight away.

    Commercial Break leaves nothing for the usual targeting to find: its
    impression is a 1x1 pixel with no frame to walk up to, and the click URL
    is assembled in JS at click time so there is no <a href> carrying the
    tracker either. What it does have is presence — it covers the viewport,
    so whatever sits topmost at the centre is the creative.

    Done immediately rather than after a screenshot round-trip, because the
    overlay dismisses itself within a few seconds and by the time a model had
    looked at a picture of it, it was gone.

    Guessing the target this way is only safe because the beacon decides:
    a click that lands elsewhere produces no click for this campaign and is
    recorded as untested, never as a pass.
    """
    vp = settings["viewport"]
    cx, cy = vp["width"] / 2, vp["height"] / 2
    try:
        info = page.evaluate(
            """([x, y]) => {
                 const el = document.elementFromPoint(x, y);
                 if (!el) return null;
                 const r = el.getBoundingClientRect();
                 return {tag: el.tagName, w: Math.round(r.width), h: Math.round(r.height)};
               }""", [cx, cy])
    except Exception:
        info = None
    if not info or info["w"] < 200 or info["h"] < 150:
        _log(meta, f"overlay click skipped: nothing large at the centre ({info})")
        return False

    since = len(recorder.beacons)
    _log(meta, f"overlay click at ({cx:.0f},{cy:.0f}) on <{info['tag'].lower()}> "
               f"{info['w']}x{info['h']}")
    watch = _TabWatch(page)
    try:
        with ctx.expect_page(timeout=8000) as popup:
            page.mouse.click(cx, cy)
        newp = popup.value
        _pause(newp, 2)
        try:
            meta["landing"] = newp.url
            _log(meta, f"landing -> {newp.url[:150]}")
            newp.close()
        except Exception:
            pass
    except Exception:
        _pause(page, 2)

    _confirm_click(recorder, meta, expected_id, since, source="overlay")
    _back_to_test_page(page, recorder, settings, meta, watch)
    return meta.get("click_result") == "confirmed"


# Where on an element it is itself the topmost thing, nearest its centre.
# Sampled inside the element's own frame, so the answer is relative to the
# element: [dx, dy] from its top-left corner, plus its size, in its frame's
# CSS pixels.
_HITTABLE = """e => {
    const r = e.getBoundingClientRect();
    const x0 = Math.max(r.left, 0), x1 = Math.min(r.right, innerWidth - 1);
    const y0 = Math.max(r.top, 0), y1 = Math.min(r.bottom, innerHeight - 1);
    if (x1 - x0 < 4 || y1 - y0 < 4) return null;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    let best = null, bestD = Infinity;
    for (let i = 0; i <= 24; i++) for (let j = 0; j <= 16; j++) {
        const x = x0 + (x1 - x0) * i / 24, y = y0 + (y1 - y0) * j / 16;
        const t = document.elementFromPoint(x, y);
        if (t && (e.contains(t) || t.contains(e)) && t !== document.body
            && t !== document.documentElement) {
            const d = (x - cx) ** 2 + (y - cy) ** 2;
            if (d < bestD) { bestD = d; best = [x - r.left, y - r.top, r.width, r.height]; }
        }
    }
    return best;
}"""


def _hittable_spot(el):
    """-> (page_x, page_y, dx, dy) for the point where `el` is on top, or None.

    page_x/page_y are in the page's viewport coordinates; dx/dy are the same
    point relative to the element, which is what an element click takes. The
    search runs in the element's own frame, and its answer used to be fed to
    page.mouse.click as if it were a page coordinate: the centre of a 300x250
    ad frame became (150,124) on the page — dziennik.pl's WIADOMOŚCI menu
    item, which the run clicked and followed. bounding_box() is in main-frame
    coordinates, frames and scaling included, so it puts the point back.
    """
    try:
        hit = el.evaluate(_HITTABLE)
        box = el.bounding_box() if hit else None
    except Exception:
        return None
    if not hit or not box:
        return None
    dx, dy, w, h = hit
    sx = box["width"] / w if w else 1.0
    sy = box["height"] / h if h else 1.0
    return box["x"] + dx * sx, box["y"] + dy * sy, dx, dy


def _hittable_point(el):
    """A point on screen where `el` itself is the topmost thing, nearest its centre.

    -> (x, y) in the page's viewport coordinates, or None when no sampled
    point is its own. A click-through anchor stretched over a whole wallpaper
    has its geometric centre under the article column; clicking there lands
    on the article.
    """
    spot = _hittable_spot(el)
    return (spot[0], spot[1]) if spot else None


def _in_main_frame(page, el):
    try:
        return el.owner_frame() is page.main_frame
    except Exception:
        return False


def _press(page, el, spot, in_main):
    """Make the click. -> None once it is made, else why it could not be.

    Never a page.mouse.click in place of an element click that failed. The
    element click is refused when something else sits over the element, and
    clicking the same spot by coordinates anyway lands on that something —
    on dziennik.pl another advertiser's interstitial, which the run then
    reported as the slot carrying another advertiser.
    """
    try:
        if spot and in_main:
            # The wallpaper case: the point was checked to be the element's
            # own in the page itself, so a plain mouse click is exact.
            page.mouse.click(spot[0], spot[1])
        elif spot:
            el.click(position={"x": spot[2], "y": spot[3]}, timeout=5000)
        else:
            el.click(timeout=5000)
        return None
    except Exception as e:
        lines = [ln.strip() for ln in str(e).splitlines() if ln.strip()]
        why = next((ln for ln in lines if "intercepts pointer events" in ln),
                   lines[0] if lines else type(e).__name__)
        return why[:140]


def _click_element(page, ctx, recorder, settings, meta, el, box, expected_id, since,
                   source="frame"):
    """Click one element, follow the tab it opens, judge the click by its
    beacon. -> "clicked", "refused" (nothing was clicked), "off-screen" or
    "no-time"."""
    vp = settings["viewport"]
    deadline = _deadline(recorder, settings)
    if _left(deadline) < CLICK_NEEDS_S:
        _log(meta, "click skipped: the run is out of time for this page")
        return "no-time"

    def centre():
        b = None
        try:
            b = el.bounding_box()
        except Exception:
            pass
        b = b or box
        return b, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    try:
        el.scroll_into_view_if_needed(timeout=5000)
        _pause(page, 1)
    except Exception:
        pass
    _box, cx, cy = centre()

    if not (0 < cx < vp["width"] and 0 < cy < vp["height"]):
        # Still off-screen. scroll_into_view_if_needed moves the minimal
        # distance and gives up on containers it cannot scroll, which leaves a
        # sidebar creative sitting below the fold — measured on
        # kultura.onet.pl, where slot.right reported y=1654 in a 900px window
        # and the click was refused while slot.top clicked fine. Centre it
        # explicitly and measure again.
        try:
            el.evaluate("e => e.scrollIntoView({block: 'center', inline: 'nearest'})")
            _pause(page, 1)
        except Exception:
            pass
        _box, cx, cy = centre()

    if not (0 < cx < vp["width"] and 0 < cy < vp["height"]):
        # Genuinely unreachable. Clicking a clamped fallback coordinate is how
        # the wrong ad gets clicked and reported as this campaign's, so refuse.
        _log(meta, f"click skipped: creative off-screen at ({cx:.0f},{cy:.0f})")
        return "off-screen"

    # Click the element, not the coordinate. Computing a centre point and
    # firing page.mouse.click() there hits whatever is topmost at that spot —
    # observed landing on an ordinary article link that had moved under the
    # creative. element.click() targets the element itself and is still a
    # trusted event (it is CDP input, unlike page.evaluate("el.click()"),
    # which publishers' overlays ignore because isTrusted is false).
    # A wallpaper's click-through anchor is as large as the page, so its centre
    # sits under the article column. Click where the element itself is on top.
    spot = _hittable_spot(el)
    if spot and not (0 <= spot[0] < vp["width"] and 0 <= spot[1] < vp["height"]):
        spot = None
    if spot and (abs(spot[0] - cx) > 1 or abs(spot[1] - cy) > 1):
        cx, cy = spot[0], spot[1]
    else:
        spot = None
    in_main = _in_main_frame(page, el)

    watch = _TabWatch(page)
    refused = None
    try:
        with ctx.expect_page(timeout=8000) as popup:
            refused = _press(page, el, spot, in_main)
            if refused:
                raise RuntimeError(refused)
            _log(meta, f"element click at ({cx:.0f},{cy:.0f})")
        newp = popup.value
        # Polled on the new tab itself, so its redirects are seen as they
        # happen; read in a time.sleep loop, newp.url never moved past the
        # first address.
        until = time.time() + max(2, min(12, _left(deadline) - 25))
        last = ""
        while time.time() < until:
            try:
                cur = newp.url
            except Exception:
                break
            if cur != last:
                last = cur
                _log(meta, f"landing -> {cur[:160]}")
            if newp.is_closed():
                break
            _pause(newp, 0.5)
        meta["landing"] = last
        try:
            newp.close()
        except Exception:
            pass
    except Exception:
        if not refused:
            _pause(page, 2)
            _log(meta, "no new tab opened by the click")

    if refused:
        watch.stop()
        _log(meta, f"click skipped: the creative would not take the click — {refused}")
        return "refused"
    _confirm_click(recorder, meta, expected_id, since, source=source)
    _back_to_test_page(page, recorder, settings, meta, watch)
    return "clicked"


def _sheet_vendors(ids):
    """The serving vendor a sheet's ids belong to, told by their shape: an
    Adform banner id (bn) runs to 8 digits — 90565344 — and a CM360
    placement id to 9 — 457786509. Before any of them fires, nothing else on
    the page says which it is."""
    out = set()
    for i in ids:
        s = str(i)
        if s.isdigit():
            out.add("CM360" if len(s) >= 9 else "Adform")
    return out


def _click_unbooked(page, ctx, recorder, settings, meta, sheet, deadline, most=2,
                    wait_out_layers=True):
    """Click the frames of impressions that fired from the sheet's own vendor
    under ids the sheet does not book. -> how many were clicked.

    The last resort when no booked impression fired and the model found
    nothing. Measured on money.pl's WP previews: the creatives fire Adform
    90626723-26, ids missing from the loaded sheet, and the model would not
    point at a 300x250 that was plainly on screen — so the click went untested
    although the frame that fired the impression is an exact handle on the
    creative. Each click is judged against that frame's own id, so the log
    says whose click it was; it is never credited to a booked id.

    An id whose click has already tracked — the model's click landed on that
    creative and was judged against the sheet — is not clicked again: the
    beacon has answered for it, and a second click would only overwrite that
    answer.
    """
    kin = _sheet_vendors(sheet)
    booked = {str(i) for i in sheet}
    answered = {str(b.get("id")) for b in recorder.beacons
                if b.get("kind") == vendors.CLICK and b.get("evidence") == "fired"}
    tried, looked = 0, set()
    for b in list(recorder.beacons):
        if tried >= most:
            break
        ident = str(b.get("id") or "")
        if (b.get("kind") != vendors.IMPRESSION or b.get("evidence") != "fired"
                or b.get("vendor") not in kin or not ident
                or ident in booked or ident in looked or ident in answered):
            continue
        looked.add(ident)
        if _left(deadline) < 40:
            _log(meta, "no time left to try the frames of unbooked impressions")
            break
        el, box = _frame_box(recorder.impression_frame(ident))
        if not box:
            continue
        tried += 1
        _log(meta, f"trying the frame of {b['vendor']} {ident}, which fired here "
                   "but is not in the sheet")
        if wait_out_layers:
            _wait_out_layer(page, settings, meta, el, deadline)
        done = _click_element(page, ctx, recorder, settings, meta, el, box, ident,
                              len(recorder.beacons), source="unbooked")
        if done == "clicked" and meta.get("click_result") == "confirmed":
            meta["click_target_id"] = ident
            _log(meta, f"note: that click belongs to {ident}, which the sheet does "
                       "not book — not to any of the campaign's booked ids")
            break
        if _page_lost(meta):
            break
    return tried


def _page_lost(meta):
    """Did a click take the test tab away for good? Then nothing more is
    clicked: whatever is on screen is some other site, not the test page."""
    gone = meta.get("navigated_away")
    return bool(gone) and not gone.get("returned")


def _click_creative(page, ctx, recorder, settings, meta, expected_id=None,
                    wait_out_layers=True):
    """Click the creative and follow where it goes.

    Uses a real mouse click on purpose. WP's Commercial Break gates on
    isTrusted, so a synthetic element.click() is accepted by the DOM and then
    ignored by the ad — producing a click that appears to happen and tracks
    nothing.

    `expected_id` is the id the click has to carry — or, when none of the
    sheet's impressions fired, the sheet's ids as a tuple. Then no frame is
    known to be ours: the only links taken are ones that carry one of those
    ids, and nothing is clicked merely for being an ad.

    `wait_out_layers` is off where the full-screen layer is itself what is
    being tested (navigation_click's Commercial Break).
    """
    if not settings.get("click", True):
        _log(meta, "click skipped (profile)")
        return

    deadline = _deadline(recorder, settings)
    if _left(deadline) < CLICK_NEEDS_S:
        _log(meta, "click skipped: the run is out of time for this page")
        return
    sheet = (tuple(str(i) for i in expected_id)
             if isinstance(expected_id, (tuple, list, set)) else None)
    if sheet:
        el, box = _clickthrough_element(page, ids=sheet)
    else:
        el, box = _creative_frame(recorder, page, expected_id)
    if wait_out_layers:
        # Also before the vision search when nothing was found: a screenshot
        # of somebody else's interstitial shows the model nothing of ours.
        _wait_out_layer(page, settings, meta, el, deadline)

    if box:
        done = _click_element(page, ctx, recorder, settings, meta, el, box,
                              expected_id, len(recorder.beacons))
        if done in ("off-screen", "no-time") or _page_lost(meta):
            return
        if done == "clicked" and meta.get("click_result") != "none":
            return
        # Clicked and nothing tracked, or the element would not take the
        # click. Deterministic targeting found *a* clickable thing, not
        # necessarily the creative (OLX Polubienia: the model sees the banner
        # the page's own link logic does not). Give the model one look before
        # reporting the click as absent.

    # Without a box, deterministic targeting found nothing — the creative is
    # neither an iframe nor a link carrying the click tracker. That is the
    # screening and wallpaper case, where the run used to stop here and the
    # placement looked click-less although nothing had been attempted. Ask the
    # model where it is, and let the beacon check decide whether the click it
    # produced belongs to this campaign.
    found = _ask_where(page, settings, meta, expected_id, deadline=deadline)
    if found:
        _clicked_at(page, ctx, recorder, settings, meta, expected_id,
                    found["x"] + found["w"] / 2, found["y"] + found["h"] / 2,
                    len(recorder.beacons), source="model",
                    wait_out_layers=wait_out_layers)
        if meta.get("click_result") == "confirmed" or _page_lost(meta):
            return
    tried = (_click_unbooked(page, ctx, recorder, settings, meta, sheet, deadline,
                             wait_out_layers=wait_out_layers)
             if sheet else 0)
    if not box and not found and not tried:
        _log(meta, "click skipped: no clickable creative frame found")


# How many screens of a page the vision fallback is willing to look through.
MAX_SCREENS = 5
# What one of those looks can take: the scroll, the screenshot, and a model
# call that gives up after 25s.
VISION_LOOK_S = 28


def _ask_where(page, settings, meta, expected_id, _again=True, deadline=None):
    """Let a model point at the creative. -> box in viewport coordinates."""
    eye = settings.get("vision")
    advertiser = settings.get("advertiser")
    if eye is None or not advertiser:
        # Say which half is missing. Returning silently here made a
        # misconfiguration indistinguishable from a model that looked and
        # found nothing, which are very different things to act on.
        _log(meta, "vision fallback unavailable: "
                   + ("no advertiser named" if not advertiser else "no model configured"))
        return None
    # The model sees one screenshot, which is one screen of the page. A 160x600
    # skyscraper in a sidebar sits well below the first screen, so on the BNP
    # DigitalContact previews four banners that fire and click perfectly were
    # reported "not tested" because the model was never shown them. Look screen
    # by screen, and leave the page scrolled where the creative was found:
    # the click that follows is in viewport coordinates.
    #
    # Always from the top. Starting wherever the page happened to be — after a
    # click, or a wait that ended deep in the page — hid everything above it,
    # and the first screen is where screenings and billboards are.
    vp = settings["viewport"]
    step = max(int(vp["height"] * 0.85), 200)
    try:
        total = page.evaluate("document.documentElement.scrollHeight") or 0
        was = page.evaluate("window.scrollY") or 0
    except Exception:
        total, was = 0, 0
    offsets = [0]
    y = 0
    while len(offsets) < MAX_SCREENS and y + step < total - vp["height"] * 0.25:
        y += step
        offsets.append(y)

    last_why = {}
    looked = 0
    for n, off in enumerate(offsets):
        # One look is a screenshot and a model call of up to 25s, and a click
        # has to fit after it.
        if _left(deadline) < VISION_LOOK_S + CLICK_NEEDS_S:
            _log(meta, "vision search cut short: the run is out of time for this page")
            break
        try:
            if n or was:
                page.evaluate("(y) => window.scrollTo(0, y)", off)
                _pause(page, 0.8)
            shot = page.screenshot(type="png")
        except Exception:
            return None
        looked += 1
        why = {}
        box = creative_click.locate(eye, shot, advertiser, vp, why)
        if why:
            last_why = why
        if box:
            _log(meta, f"model located creative at ({box['x']:.0f},{box['y']:.0f}) "
                       f"{box['w']:.0f}x{box['h']:.0f} conf={box['confidence']}"
                       + (f" on screen {n + 1} of {len(offsets)}" if n else "")
                       + (f" — {box['reason'][:70]}" if box.get("reason") else ""))
            return box
    try:
        page.evaluate("(y) => window.scrollTo(0, y)", 0)
    except Exception:
        pass
    _log(meta, "model could not locate the creative"
               + (f" (looked through {looked} screens)" if looked > 1 else "")
               + (f" — model call failed: {last_why['error']}" if last_why.get("error")
                  else f" — last answer: {last_why['reply']}" if last_why.get("reply") else ""))
    if _again and _left(deadline) >= 2 * VISION_LOOK_S + CLICK_NEEDS_S:
        # The model's answer on the same page differs from one look to the
        # next (wp.pl mobile: found on one run, "nothing" on the next). One
        # more pass costs a few seconds; a missed click costs a wrong report.
        _log(meta, "looking once more")
        _pause(page, 3)
        return _ask_where(page, settings, meta, expected_id, _again=False, deadline=deadline)
    return None


def _clicked_at(page, ctx, recorder, settings, meta, expected_id, cx, cy,
                since, source, wait_out_layers=True):
    """A real mouse click at a point, then judge it by the beacon."""
    deadline = _deadline(recorder, settings)
    if _left(deadline) < CLICK_NEEDS_S:
        _log(meta, "click skipped: the run is out of time for this page")
        return
    if source == "model" and wait_out_layers:
        # The model looked at a screenshot taken a moment ago; a layer that has
        # come up since would take this click.
        _wait_out_layer(page, settings, meta, None, deadline)
        since = max(since, len(recorder.beacons))
    watch = _TabWatch(page)
    _log(meta, f"{source} click at ({cx:.0f},{cy:.0f})")
    try:
        with ctx.expect_page(timeout=8000) as popup:
            page.mouse.click(cx, cy)
        newp = popup.value
        _pause(newp, 2)
        try:
            meta["landing"] = newp.url
            _log(meta, f"landing -> {newp.url[:160]}")
            newp.close()
        except Exception:
            pass
    except Exception:
        _pause(page, 2)
        _log(meta, "no new tab opened by the click")

    _confirm_click(recorder, meta, expected_id, since, source=source)
    _back_to_test_page(page, recorder, settings, meta, watch)


def _confirm_click(recorder, meta, expected_id, since, source):
    """Whether the click that just happened belongs to this campaign.

    This is what makes clicking safe to attempt at all. A click that lands on
    a competitor's creative — because the slot refreshed, or because the model
    pointed at the wrong one — produces somebody else's beacon, and is
    recorded as exactly that rather than as this campaign's click working.
    """
    # Give the beacon time to arrive. A click tracker fires from the tab the
    # click opened, and checking once a couple of seconds later reported "no
    # click beacon followed" for clicks the HAR shows landing correctly —
    # a contradiction between the live log and the verdict. The wait has to
    # let Playwright deliver events (recorder.sleep), or nothing that arrives
    # during it is seen until it is over.
    deadline = time.time() + 8
    verdict, ident = creative_click.click_confirmed(recorder, expected_id, since)
    while verdict != "confirmed" and time.time() < deadline:
        recorder.sleep(0.4)
        verdict, ident = creative_click.click_confirmed(recorder, expected_id, since)
    meta["click_result"] = verdict
    if verdict == "confirmed":
        _log(meta, f"click confirmed by beacon {ident} ({source})")
    elif verdict == "unattributed":
        _log(meta, f"a click tracked for {ident}, but nothing said which id to "
                   f"expect — it cannot be credited to this campaign")
    elif verdict == "other_advertiser":
        _log(meta, f"click tracked for a DIFFERENT id ({ident}) — not this "
                   f"campaign; the slot is carrying another advertiser")
    else:
        _log(meta, f"clicked ({source}) but no click beacon followed")


def _campaign_fired(recorder, expected, ids):
    """Has this campaign's impression fired — not just anybody's?

    With an expected id that is the whole question. In a scan there is only the
    sheet's set of ids, and any one of them counts. With neither (no sheet),
    any impression does, as it always did.
    """
    if expected:
        return recorder.has(kind=vendors.IMPRESSION, ident=expected)
    if ids:
        return any(recorder.has(kind=vendors.IMPRESSION, ident=i) for i in ids)
    return recorder.has(kind=vendors.IMPRESSION)


def _aim_id(recorder, expected, ids):
    """The id a click should be judged against: the explicit one, else
    whichever of the sheet's ids actually fired, else none."""
    if expected:
        return expected
    for b in recorder.beacons:
        if (b.get("kind") == vendors.IMPRESSION and b.get("evidence") == "fired"
                and str(b.get("id")) in ids):
            return str(b["id"])
    return None


def _click_target_id(recorder, meta, target, settings=None):
    """Which ID the click should go after, and whether to click at all.

    -> (expected_id, go). With an expected ID there is nothing to decide. With
    only the sheet's IDs (a scan), aim at whichever of them actually fired:
    that is the creative on screen, and it is the ID the click beacon has to
    carry. When none of them fired there is no campaign creative to click, so
    the honest answer is "not tested" rather than a click on whatever frame is
    there — recorded on dziennik.pl, where such a click landed on an empty slot
    and the report read "click: no" against a click tag nobody had tried.
    """
    if target.get("expected_id"):
        return target["expected_id"], True
    ids = [str(i) for i in (target.get("wait_for") or []) if i]
    if not ids:
        return None, True                  # no sheet: behave as before
    for b in recorder.beacons:
        if (b.get("kind") == vendors.IMPRESSION and b.get("evidence") == "fired"
                and str(b.get("id")) in ids):
            return str(b["id"]), True
    if settings and settings.get("vision") is not None and settings.get("advertiser"):
        # No booked impression fired — but a creative can be on screen without
        # one (OLX Polubienia and the deaz.io preview carry no CM360 impression
        # pixel at all). Let the model look; the click only counts if its
        # beacon carries one of the sheet's ids, so a wrong guess is discarded.
        _log(meta, "no booked impression fired — looking for the creative on screen instead")
        return tuple(ids), True
    _log(meta, "click skipped: none of this campaign's creatives appeared, "
               "so there was nothing of ours to click")
    return None, False


# ── strategies ────────────────────────────────────────────────────────────

def load(page, ctx, recorder, settings, meta, target):
    """Plain load. Correct for isolated creative previews."""
    _goto(page, target["url"], meta)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))
    _scroll(page, settings)
    _wait_for_impression(recorder, settings, meta, target.get("expected_id"),
                         target.get("wait_for"), page=page)
    aim, go = _click_target_id(recorder, meta, target, settings)
    if go:
        _click_creative(page, ctx, recorder, settings, meta, aim)


# How long the first load of a preview gets to serve the campaign before the
# page is reloaded. strefabiznesu.pl served at 7s.
FIRST_LOAD_GRACE = 12


def gam_preview(page, ctx, recorder, settings, meta, target):
    """Ad Manager / Bankier preview links need loading twice.

    The first request only sets the preview cookie; the creative is served on
    the next one. Loading once and reporting nothing found is a false
    negative — the page was never in the state being tested.
    """
    url = target["url"]
    _goto(page, url, meta)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))
    _log(meta, "first load (sets preview cookie)")

    # A preview link that carries its own token often serves on the first load.
    # Reloading such a page is not free: strefabiznesu.pl rendered the BNP
    # creative on the first load (CM360 impression at 7s) and answered the
    # reload with a Cloudflare "are you human" challenge, so the click and the
    # IAS check ran against a bot wall instead of the ad. When the sheet says
    # which IDs are ours and one has already fired, the reload has nothing to add.
    ours = {str(i) for i in (target.get("wait_for") or []) if i}
    if target.get("expected_id"):
        ours.add(str(target["expected_id"]))
    served = bool(ours) and recorder.wait_for(
        lambda: any(recorder.has(kind=vendors.IMPRESSION, ident=i) for i in ours),
        FIRST_LOAD_GRACE, settings.get("poll_interval", 0.5))
    if served:
        _log(meta, "campaign creative already served on the first load — not reloading")
    else:
        _pause(page, 2)
        _goto(page, url, meta)
        _log(meta, "second load (renders creative)")
        consent.accept(page, 1.5)
    _scroll(page, settings)
    _wait_for_impression(recorder, settings, meta, target.get("expected_id"),
                         target.get("wait_for"), page=page)
    aim, go = _click_target_id(recorder, meta, target, settings)
    if go:
        _click_creative(page, ctx, recorder, settings, meta, aim)


def _click_link(page, loc, meta):
    """Click a link, recovering from an intercepted click.

    Playwright scrolls the target the minimal distance into view, so on a page
    with a sticky header the link lands right under it and every retry is
    intercepted until the timeout — measured on wiadomosci.wp.pl, where all
    eight navigation attempts failed this way and the Commercial Break overlay
    consequently never appeared. A person would scroll it into open view, so
    on failure centre it and try again.
    """
    try:
        loc.scroll_into_view_if_needed(timeout=4000)
    except Exception:
        pass
    try:
        loc.click(timeout=8000)
        return
    except Exception:
        pass

    try:
        loc.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
        _pause(page, 0.5)
    except Exception:
        pass
    try:
        loc.click(timeout=8000)
        _log(meta, "    click landed after centring the link")
        return
    except Exception:
        pass

    # Last resort: a real mouse click at the link's own box. Still a trusted
    # event, which the overlay requires, but it hits whatever is topmost —
    # acceptable only because nothing else worked and a failed navigation is
    # itself reported.
    box = loc.bounding_box()
    if not box:
        raise RuntimeError("link has no box to click")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    _log(meta, "    click landed via mouse at the link's box")


def navigation_click(page, ctx, recorder, settings, meta, target):
    """Commercial Break: the overlay only appears on a real in-page navigation.

    page.goto() to an article does not trigger it — the publisher hooks link
    clicks. So this clicks real links until the overlay fires.
    """
    url = target["url"]
    _goto(page, url, meta)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))
    _pause(page, 3)

    exclude = settings.get("exclude_links")
    exclude_rx = re.compile(exclude, re.I) if exclude else None
    # Split on the query and fragment too, not just the path. A preview link
    # without a trailing slash — `https://kobieta.wp.pl?wfName=…` — left the
    # whole query string as the "host", so no link on the page contained it and
    # the run found zero candidates, reported no overlay, and called a working
    # placement untagged.
    host = re.split(r"[/?#]", re.sub(r"^https?://(www\.)?", "", url))[0]

    try:
        # Only links a person could actually click. Collecting every a[href]
        # put the category menu first — spoleczenstwo, sadownictwo, nato — and
        # those live in a flyout that is hidden until hover, so Playwright
        # waited for actionability on each in turn and timed out eight times
        # over without a single navigation. No navigation means no Commercial
        # Break overlay, which the run then reported as "no tag fired".
        links = page.evaluate(
            """(host) => Array.from(document.querySelectorAll('a[href]'))
                   .filter(a => {
                     const r = a.getBoundingClientRect();
                     if (r.width < 80 || r.height < 20) return false;   // icons, hidden
                     if (!a.offsetParent) return false;                 // display:none subtree
                     const st = getComputedStyle(a);
                     if (st.visibility === 'hidden' || st.pointerEvents === 'none') return false;
                     // An article headline carries real text; nav items are short.
                     return (a.innerText || '').trim().length >= 25;
                   })
                   .map(a => a.href)
                   .filter(h => h.includes(host) && h.length > 25)""",
            host)
    except Exception:
        links = []

    # Shop, login, newsletter and live-stream pages are not articles; clicking
    # them navigates somewhere that tears the run down without ever showing an
    # overlay.
    if exclude_rx:
        links = [h for h in links if not exclude_rx.search(h)]
    links = list(dict.fromkeys(links))
    _log(meta, f"{len(links)} candidate article links")

    expected = target.get("expected_id")
    # In a scan there is no single expected id, only the sheet's. Without this
    # the loop below stopped at the first impression of anyone — on a portal
    # carrying other advertisers' interstitials that ends the search before the
    # campaign's own has had a chance — and the click was judged against
    # nothing, so a click that tracked the right placement read "unattributed".
    ids = {str(i) for i in (target.get("wait_for") or []) if i}
    budget = settings["patience"]
    per_click = max(12, budget // max(1, settings.get("max_link_clicks", 8)))

    deadline = _deadline(recorder, settings)
    for i, href in enumerate(links[:settings.get("max_link_clicks", 8)], 1):
        if not consent.alive(page):
            _log(meta, "page closed — stopping")
            break
        if _campaign_fired(recorder, expected, ids):
            break
        # One more navigation is a link click, up to 22s watching for the
        # overlay, the wait for its impression and a way back: ~70s. Eight of
        # them do not fit in the run's budget on a slow portal.
        if _left(deadline) < 70:
            _log(meta, f"stopping after {i - 1} navigations: the run is out of time for this page")
            break
        _log(meta, f"[{i}] navigating via link click -> {href[:90]}")
        try:
            loc = page.locator(f'a[href="{href}"]').first
            _click_link(page, loc, meta)       # real click: CB checks isTrusted
        except Exception as e:
            _log(meta, f"    link click failed: {str(e)[:80]}")
            continue

        # Watch for the interstitial from the instant the link is clicked,
        # rather than after the navigation has settled — it is shown during
        # the transition, and by the time the page is quiet it has gone.
        panel = _await_overlay(page, settings.get("overlay_wait", 12))
        if panel:
            _log(meta, f"    overlay on screen: <{panel['tag'].lower()}> "
                       f"{panel['w']}x{panel['h']} z={panel['z']}")
            # The shield goes up before the creative is in it. Clicking the
            # moment it appears lands on nothing (the bank client's Adform Commercial
            # Break: the click link arrives a second or two later and the
            # overlay is gone a few seconds after that), so wait for a
            # link that fills the screen and click that.
            spot = _wait_overlay_link(page, settings.get("overlay_link_wait", 10))
            if spot:
                _log(meta, "    the creative's link is in the overlay")
            px, py = spot or (panel["x"], panel["y"])
            since = len(recorder.beacons)
            try:
                page.mouse.click(px, py)
            except Exception as e:
                _log(meta, f"    overlay click failed: {str(e)[:60]}")
            _pause(page, 2)
            _confirm_click(recorder, meta,
                           _aim_id(recorder, expected, ids) or (tuple(sorted(ids)) or None),
                           since, source="overlay")
            if meta.get("click_result") == "confirmed":
                _log(meta, "    overlay fired")
                return

        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        consent.accept(page, 1.5)
        got = recorder.wait_for(
            lambda: _campaign_fired(recorder, expected, ids),
            per_click, settings.get("poll_interval", 0.5))
        if got:
            _log(meta, "    overlay fired")
            # Click it now, while it is on screen. A Commercial Break dismisses
            # itself after a few seconds, so deferring this until the strategy
            # returns meant the screenshot showed an ordinary article page and
            # the run reported a click it never had anything to click.
            #
            # Aim at the overlay itself first: it covers the viewport and the
            # usual targeting has nothing to grip on here. Fall back to the
            # normal path only if that produced no click for this campaign.
            aim = _aim_id(recorder, expected, ids)
            if not _click_overlay(page, ctx, recorder, settings, meta, aim):
                # The full-screen layer here is the creative under test, not
                # something in the way: never wait for it to go.
                _click_creative(page, ctx, recorder, settings, meta, aim,
                                wait_out_layers=False)
            return
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _pause(page, 2)
            consent.accept(page, 1.5)
        except Exception:
            break

    # No overlay ever appeared. Nothing to click, and saying so is the finding.
    _log(meta, "no overlay appeared in any navigation")


def watch(page, ctx, recorder, settings, meta, target):
    """Hand the browser to a person and record what fires.

    For pages where automated clicking is not trustworthy: several identical
    slots competing for the same creative, overlays that are not iframes, or
    sandboxed previews that block navigation outright. Automating the click
    there produced confident verdicts about competitors' ads. A person clicks
    correctly in seconds; the value this tool adds is capturing the evidence,
    not the clicking.
    """
    _goto(page, target["url"], meta)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))

    budget = settings.get("watch_timeout", 300)
    _log(meta, f"watch mode: browser is yours for up to {budget}s")

    # Two ways to be told the person has finished, because there are two ways
    # to drive this. From the CLI it is Ctrl+C. Over the API there is no
    # console to interrupt, so the caller passes `stop_check` — a callable the
    # HTTP layer flips when the operator says they are done. Without it an
    # API-driven watch could only ever end by timing out, leaving the reviewer
    # waiting and a browser window open behind them.
    stop_check = settings.get("stop_check")
    announce = settings.get("announce", True)
    if announce:
        print(f"\n  >>> {meta['label']}")
        print(f"      {target['url'][:110]}")
        print("      Click the creative in the browser window. Ctrl+C when done.\n")

    deadline = time.time() + budget
    shown = 0
    try:
        while time.time() < deadline and consent.alive(page):
            if stop_check is not None and stop_check():
                _log(meta, "watch ended by operator")
                break
            if len(recorder.beacons) != shown:
                shown = len(recorder.beacons)
                if announce:
                    for b in recorder.beacons[-3:]:
                        if b["evidence"] == "fired":
                            print(f"      [{b['t']:>5.1f}s] {b['vendor']:<12} "
                                  f"{b['kind']:<10} {b['id']}")
            time.sleep(0.5)
        else:
            # Reached without a break: either the budget ran out, or the person
            # simply closed the window — which is also a way of saying "done",
            # and should not be reported as a timeout.
            _log(meta, f"watch ran its full {budget}s" if time.time() >= deadline
                 else "watch ended: browser window was closed")
    except KeyboardInterrupt:
        _log(meta, "watch ended by user")


# ── instream video ────────────────────────────────────────────────────────

# Play controls, by the words publishers put on them. Deliberately short: a
# broadcaster's own navigation is full of the same words ("Oglądaj" is a
# top-level menu item on tvn24.pl), so the label alone is not enough and the
# candidate also has to sit near the player — see _play_control.
PLAY_LABELS = ("odtwórz", "oglądaj", "obejrzyj", "włącz", "play", "wznów")

_PLAYER_BOX = """() => {
    // The biggest <video> on the page, or failing that the biggest element
    // calling itself a player. Viewport coordinates.
    const boxes = [];
    for (const v of document.querySelectorAll('video, [class*=player], [id*=player]')) {
        const r = v.getBoundingClientRect();
        if (r.width > 200 && r.height > 120) boxes.push({
            x: r.x + r.width / 2, y: r.y + r.height / 2,
            w: r.width, h: r.height, top: r.y, area: r.width * r.height,
            // A <video> that is actually running is the spot; a paused one or
            // a wrapper div is scenery. Clicking scenery is how a run reports
            // "no click beacon" having never touched the ad.
            playing: (v.tagName === 'VIDEO' && !v.paused && v.currentTime > 0) ? 1 : 0,
            video: v.tagName === 'VIDEO' ? 1 : 0});
    }
    if (!boxes.length) return null;
    boxes.sort((a, b) => (b.playing - a.playing) || (b.video - a.video) || (b.area - a.area));
    return boxes[0];
}"""

_PLAY_CANDIDATES = r"""(labels) => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const out = [];
    for (const e of document.querySelectorAll('button, a, [role=button], [class*=play]')) {
        const shown = norm(e.innerText);
        const t = shown || norm(e.getAttribute('aria-label'));
        if (!t || t.length > 24) continue;
        if (!labels.some(l => t === l || t.startsWith(l))) continue;
        if (e.closest('nav, header, [class*=nav], [class*=menu]')) continue;
        const r = e.getBoundingClientRect();
        if (r.width < 20 || r.height < 12) continue;
        out.push({x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
                  // Does the button say what it does, or is it an icon with a
                  // label only a screen reader sees? On vod.tvp.pl the icon in
                  // the hero trailer's control bar sits nearer the player than
                  // the page's actual "ODTWÓRZ" button, and picking by
                  // distance alone pressed the wrong one and played nothing.
                  labelled: shown ? 1 : 0, area: r.width * r.height,
                  label: t.slice(0, 24)});
    }
    return out;
}"""

# Is a spot on screen right now? The IMA SDK puts its own container over the
# player while an ad runs and takes it away afterwards.
_AD_PLAYING = """() => {
    for (const sel of ['.ima-ad-container', '[id*=ima-ad]', '[class*=ad-container]',
                       '[class*=adContainer]', '[class*=videoAdUi]']) {
        for (const e of document.querySelectorAll(sel)) {
            const r = e.getBoundingClientRect();
            if (r.width > 200 && r.height > 120) return true;
        }
    }
    return false;
}"""


def _keep_active(page):
    """Keep the tab fronted and the page looking interacted-with.

    Measured on vod.tvp.pl: the same run requested its pre-roll at 30.7s with
    the window fronted and at 232.5s without — the player defers while Chrome
    treats the tab as occluded. A 90s budget therefore reported "no tags" on
    a page whose only problem was that nobody was looking at it.
    """
    try:
        page.bring_to_front()
        page.mouse.move(700, 450)
    except Exception:
        pass


def _play_control(page, meta):
    """The play button, if this player needs one pressed. -> (x, y) or None."""
    try:
        box = page.evaluate(_PLAYER_BOX)
        cands = page.evaluate(_PLAY_CANDIDATES, list(PLAY_LABELS))
    except Exception:
        return None
    if not cands:
        return None
    if box:
        # Near the player, or not at all. The alternative is clicking the
        # site's own "Oglądaj" menu item and navigating off the test page —
        # which is how one run lost its pre-roll a second after requesting it.
        cands = [c for c in cands if abs(c["y"] - box["y"]) < box["h"] + 400]
        if not cands:
            return None
        cands.sort(key=lambda c: (-c.get("labelled", 0), -c.get("area", 0),
                                  (c["x"] - box["x"]) ** 2 + (c["y"] - box["y"]) ** 2))
    c = cands[0]
    _log(meta, f"play control '{c['label']}' at ({c['x']},{c['y']})")
    return c["x"], c["y"]


def _serving_impressions(recorder):
    return {b["id"] for b in recorder.beacons
            if b.get("kind") == vendors.IMPRESSION
            and b.get("evidence") == "fired"
            and b.get("vendor") in vendors.SERVING_VENDORS and b.get("id")}


def _await_video(page, recorder, expected_id, budget, ids=()):
    """Wait for a spot to start, keeping the tab alive. -> what started.

    Returns "expected", "other" or None. Stopping on *any* serving impression
    rather than only the expected one matters more than it looks: instream is
    routinely trafficked as two spots in rotation, and waiting out the full
    budget for the 30s creative while the 15s one played and finished left
    the click landing on an empty player 160s later.

    `ids` are the sheet's ids when a scan has no single expected one: any of
    them counts as the campaign's own spot.
    """
    mine = ({expected_id} if expected_id else set()) | {str(i) for i in ids}
    deadline = time.time() + budget
    while True:
        served = _serving_impressions(recorder)
        if mine & served:
            return "expected"
        if served:
            return "other"
        if time.time() >= deadline:
            return None
        _keep_active(page)
        _pause(page, 1.0)


# How long a pod gets to reach the campaign's own spot after somebody else's
# played first. TVN's test page plays other advertisers' spots ahead of the
# one under test; clicking the first one tested a click that was not ours.
POD_WAIT_S = 45


def _await_own_spot(page, recorder, expected_id, ids, budget):
    mine = ({expected_id} if expected_id else set()) | {str(i) for i in ids}
    deadline = time.time() + budget
    while time.time() < deadline:
        if mine & _serving_impressions(recorder):
            return True
        _keep_active(page)
        _pause(page, 1.0)
    return False


def video(page, ctx, recorder, settings, meta, target):
    """Instream pre-roll: start the player, then click the spot itself.

    Two things make this unlike every display strategy. Nothing serves until
    playback begins, so the run may have to press play; and the click target
    is the spot on screen rather than a creative iframe — the IMA SDK lays a
    clickthrough layer over the video, and a real click on it opens the
    advertiser's page in a new tab, which is what fires
    `track.adform.net/C/?bn=`.
    """
    expected_id = target.get("expected_id")
    sheet_ids = [str(i) for i in (target.get("wait_for") or []) if i]
    _goto(page, target["url"], meta)
    _keep_active(page)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))
    if consent.still_up(page):
        # Worth saying plainly: a page behind the wall serves nothing at all,
        # so every verdict that followed would really be about the wall.
        _log(meta, "consent wall still up after accept — nothing will serve")
    _keep_active(page)

    # Give autoplay its chance first. TVN's test page starts the pre-roll on
    # its own, and there pressing play is not merely unnecessary — it is how
    # the run navigates away from the page it is meant to be testing.
    grace = min(settings.get("play_wait", 12), settings["patience"])
    started = _await_video(page, recorder, expected_id, grace, sheet_ids)
    if started is None and settings.get("play", "auto") != "none":
        spot = _play_control(page, meta)
        if spot:
            try:
                page.mouse.click(*spot)
            except Exception as e:
                _log(meta, f"play click failed: {type(e).__name__}")
        else:
            _log(meta, "no play control found; waiting for autoplay")
        started = _await_video(page, recorder, expected_id,
                               max(settings["patience"] - grace, 10), sheet_ids)

    _log(meta, f"video impression {'seen' if started else 'NOT seen'} "
               f"within {settings['patience']}s")
    if started is None:
        return
    # Whose click we are about to test. Normally the campaign's own creative;
    # when a different one played it is that one, and saying so is the whole
    # point — judging the click against an id that never appeared reported a
    # click that landed perfectly on `?bn=90116854` as "the slot is carrying
    # another advertiser", which is not what a rotation partner is.
    click_target = expected_id
    if started == "other" and (expected_id or sheet_ids):
        _log(meta, f"another spot played first — waiting up to {POD_WAIT_S}s for the campaign's own")
        if _await_own_spot(page, recorder, expected_id, sheet_ids, POD_WAIT_S):
            started = "expected"
    if started == "expected" and not expected_id and sheet_ids:
        click_target = _aim_id(recorder, None, set(sheet_ids))
    if started == "other":
        other = sorted(_serving_impressions(recorder) - {expected_id})
        click_target = other[0] if len(other) == 1 else None
        _log(meta, "expected creative did not play; a different one did "
                   f"({', '.join(other[:3]) or 'unidentified'}) — clicking it "
                   "so the click is still tested")
        meta["click_target_id"] = click_target

    if not settings.get("click", True):
        _log(meta, "click skipped by profile")
        return

    # The spot is on screen now and will not be for long — a 15s pre-roll is
    # gone in 15 seconds — so the click goes in here rather than after the
    # usual settling.
    try:
        box = page.evaluate(_PLAYER_BOX)
    except Exception:
        box = None
    if not box:
        _log(meta, "click skipped: no player on screen to click")
        return
    try:
        playing = page.evaluate(_AD_PLAYING)
    except Exception:
        playing = False
    _log(meta, "ad container visible" if playing
         else "no ad container found; clicking the player anyway")
    # An index into the recorder, not a timestamp: click_confirmed slices the
    # beacon list with it.
    since = len(recorder.beacons)
    # Above the control bar — the middle of the bottom strip is the pause
    # button, and hitting it stops the spot without testing anything — and
    # inside the window, since a player taller than the viewport would
    # otherwise put the click off-screen.
    vp = settings["viewport"]
    cx = min(max(box["x"], 5), vp["width"] - 5)
    cy = min(max(box["top"] + box["h"] * 0.4, 5), vp["height"] - 80)
    _clicked_at(page, ctx, recorder, settings, meta, click_target,
                cx, cy, since, "video")
    if started == "other" and meta.get("click_result") == "confirmed":
        _log(meta, f"note: that click belongs to {click_target}, the creative "
                   f"that played — not to {expected_id}, which never served")

    # Neither a beacon nor a clickthrough tab. A spot with no click tracker
    # would still have opened the advertiser's page, so this is not evidence
    # of a missing tag — it means the click never reached the ad. Measured on
    # vod.tvp.pl, whose player takes the click as play/pause and logs
    # `video_player_off` while the IMA SDK never sees it. Saying "no click"
    # here would raise a defect against a tag nobody has tested.
    if meta.get("click_result") == "none" and not meta.get("landing"):
        meta["click_result"] = "not_testable"
        _log(meta, "the player consumed the click instead of the ad — the "
                   "click cannot be tested automatically on this one; use watch")


# Strategies that cannot run in a headless browser. Only "watch": it hands the
# window to a person. "video" used to be here on the strength of a tab Chrome
# treats as occluded deferring its pre-roll for minutes — true of a headed
# window behind others, not of a headless one: TVN's pre-roll played at 31s
# headless. A scan runs in the background; nothing opens on screen.
NEEDS_WINDOW = {"watch"}

_STRATEGIES = {
    "load": load,
    "gam_preview": gam_preview,
    "navigation_click": navigation_click,
    "watch": watch,
    "video": video,
}
