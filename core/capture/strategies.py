"""How to drive a page, per site shape.

Four strategies, chosen by profile. Each one takes the same arguments and
records what it did into `meta["events"]`, so the artifact says not just what
fired but what the tool did to make it fire.
"""

import re
import time

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


def _scroll(page, settings):
    """Lazy-loaded slots need the viewport to move past them."""
    for i in range(settings.get("scroll_passes", 6)):
        try:
            page.evaluate("(y) => window.scrollBy(0, y)", settings.get("scroll_step", 500))
        except Exception:
            return
        time.sleep(0.8)
    try:
        page.evaluate("() => window.scrollTo(0, 0)")
    except Exception:
        pass


def _wait_for_impression(recorder, settings, meta, expected_id=None):
    """Poll for the campaign's impression beacon.

    Waiting long enough is the single most consequential setting here. A
    publisher whose stack takes 90s looks identical to one with no tag
    implemented if the budget is 10s, and the second reading is the one that
    gets reported to the publisher as a fault.
    """
    def seen():
        if expected_id:
            return recorder.has(kind=vendors.IMPRESSION, ident=expected_id)
        return recorder.has(kind=vendors.IMPRESSION)

    ok = recorder.wait_for(seen, settings["patience"], settings.get("poll_interval", 0.5))
    _log(meta, f"impression {'seen' if ok else 'NOT seen'} within {settings['patience']}s")
    return ok


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
    """
    target_frame = recorder.impression_frame(expected_id)
    if target_frame is None:
        # No impression means no evidence of which frame is ours. Falling back
        # to "the first frame over 50x50" reads as a reasonable guess and is
        # not one: measured on wiadomosci.wp.pl it picked a competitor's
        # creative and followed it to admaster.cc. On a page full of ad frames
        # that guess is wrong more often than right, so make none — the
        # identity-based paths below still apply.
        return _clickthrough_element(page)

    for fr in [target_frame]:
        cur = fr
        while cur is not None:
            try:
                el = cur.frame_element()
                box = el.bounding_box()
            except Exception:
                box = None
            if box and box["width"] >= 50 and box["height"] >= 50:
                return el, box
            cur = getattr(cur, "parent_frame", None)

    # No iframe to click. That is not a failure — plenty of creatives render
    # as an element in the main document (static banners, screening
    # wallpapers), and the frame that fired their pixel is the page itself,
    # which has no frame element to walk up to.
    #
    # Fall back to the click-through link. Matching on the click tracker in
    # the href identifies the creative outright, so unlike a size or position
    # guess it cannot land on a competitor's ad sitting in the same page.
    return _clickthrough_element(page)


CLICK_HREF_HINTS = ("track.adform.net/C/", "adclick.g.doubleclick.net",
                    "ad.doubleclick.net/ddm/trackclk", "/ddm/clk")


def _clickthrough_element(page):
    """An <a> whose href is the campaign's click tracker, in any frame."""
    for fr in page.frames:
        try:
            handle = fr.evaluate_handle(
                """(hints) => {
                    const as = Array.from(document.querySelectorAll('a[href]'));
                    return as.find(a => hints.some(h => a.href.includes(h))) || null;
                }""",
                list(CLICK_HREF_HINTS))
            el = handle.as_element()
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
        time.sleep(poll)
    return None


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
    try:
        with ctx.expect_page(timeout=8000) as popup:
            page.mouse.click(cx, cy)
        newp = popup.value
        time.sleep(2)
        try:
            meta["landing"] = newp.url
            _log(meta, f"landing -> {newp.url[:150]}")
            newp.close()
        except Exception:
            pass
    except Exception:
        time.sleep(2)

    _confirm_click(recorder, meta, expected_id, since, source="overlay")
    return meta.get("click_result") == "confirmed"


def _click_creative(page, ctx, recorder, settings, meta, expected_id=None):
    """Click the creative and follow where it goes.

    Uses a real mouse click on purpose. WP's Commercial Break gates on
    isTrusted, so a synthetic element.click() is accepted by the DOM and then
    ignored by the ad — producing a click that appears to happen and tracks
    nothing.
    """
    if not settings.get("click", True):
        _log(meta, "click skipped (profile)")
        return

    since = len(recorder.beacons)
    el, box = _creative_frame(recorder, page, expected_id)

    if not box:
        # Deterministic targeting found nothing — the creative is neither an
        # iframe nor a link carrying the click tracker. That is the screening
        # and wallpaper case, where the run used to stop here and the
        # placement looked click-less although nothing had been attempted.
        # Ask the model where it is, and let the beacon check below decide
        # whether the click it produced belongs to this campaign.
        found = _ask_where(page, settings, meta, expected_id)
        if found:
            _clicked_at(page, ctx, recorder, settings, meta, expected_id,
                        found["x"] + found["w"] / 2, found["y"] + found["h"] / 2,
                        since, source="model")
            return
        _log(meta, "click skipped: no clickable creative frame found")
        return

    vp = settings["viewport"]

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
        time.sleep(1)
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
            time.sleep(1)
        except Exception:
            pass
        _box, cx, cy = centre()

    if not (0 < cx < vp["width"] and 0 < cy < vp["height"]):
        # Genuinely unreachable. Clicking a clamped fallback coordinate is how
        # the wrong ad gets clicked and reported as this campaign's, so refuse.
        _log(meta, f"click skipped: creative off-screen at ({cx:.0f},{cy:.0f})")
        return

    # Click the element, not the coordinate. Computing a centre point and
    # firing page.mouse.click() there hits whatever is topmost at that spot —
    # observed landing on an ordinary article link that had moved under the
    # creative. element.click() targets the element itself and is still a
    # trusted event (it is CDP input, unlike page.evaluate("el.click()"),
    # which publishers' overlays ignore because isTrusted is false).
    _log(meta, f"click element at ({cx:.0f},{cy:.0f})")
    try:
        with ctx.expect_page(timeout=8000) as popup:
            try:
                el.click(timeout=5000)
            except Exception:
                page.mouse.click(cx, cy)      # last resort
        newp = popup.value
        deadline = time.time() + 12
        last = ""
        while time.time() < deadline:
            try:
                cur = newp.url
            except Exception:
                break
            if cur != last:
                last = cur
                _log(meta, f"landing -> {cur[:160]}")
            time.sleep(0.5)
        meta["landing"] = last
        try:
            newp.close()
        except Exception:
            pass
    except Exception:
        time.sleep(2)
        _log(meta, "no new tab opened by the click")

    _confirm_click(recorder, meta, expected_id, since, source="frame")


def _ask_where(page, settings, meta, expected_id):
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
    try:
        shot = page.screenshot(type="png")
    except Exception:
        return None
    box = creative_click.locate(eye, shot, advertiser, settings["viewport"])
    if not box:
        _log(meta, "model could not locate the creative")
        return None
    _log(meta, f"model located creative at ({box['x']:.0f},{box['y']:.0f}) "
               f"{box['w']:.0f}x{box['h']:.0f} conf={box['confidence']}"
               + (f" — {box['reason'][:70]}" if box.get("reason") else ""))
    return box


def _clicked_at(page, ctx, recorder, settings, meta, expected_id, cx, cy,
                since, source):
    """A real mouse click at a point, then judge it by the beacon."""
    _log(meta, f"{source} click at ({cx:.0f},{cy:.0f})")
    try:
        with ctx.expect_page(timeout=8000) as popup:
            page.mouse.click(cx, cy)
        newp = popup.value
        time.sleep(2)
        try:
            meta["landing"] = newp.url
            _log(meta, f"landing -> {newp.url[:160]}")
            newp.close()
        except Exception:
            pass
    except Exception:
        time.sleep(2)
        _log(meta, "no new tab opened by the click")

    _confirm_click(recorder, meta, expected_id, since, source=source)


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
    # a contradiction between the live log and the verdict.
    deadline = time.time() + 8
    verdict, ident = creative_click.click_confirmed(recorder, expected_id, since)
    while verdict != "confirmed" and time.time() < deadline:
        time.sleep(0.4)
        verdict, ident = creative_click.click_confirmed(recorder, expected_id, since)
    meta["click_result"] = verdict
    if verdict == "confirmed":
        _log(meta, f"click confirmed by beacon {ident} ({source})")
    elif verdict == "other_advertiser":
        _log(meta, f"click tracked for a DIFFERENT id ({ident}) — not this "
                   f"campaign; the slot is carrying another advertiser")
    else:
        _log(meta, f"clicked ({source}) but no click beacon followed")


# ── strategies ────────────────────────────────────────────────────────────

def load(page, ctx, recorder, settings, meta, target):
    """Plain load. Correct for isolated creative previews."""
    page.goto(target["url"], wait_until="load", timeout=60000)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))
    _scroll(page, settings)
    _wait_for_impression(recorder, settings, meta, target.get("expected_id"))
    _click_creative(page, ctx, recorder, settings, meta, target.get("expected_id"))


def gam_preview(page, ctx, recorder, settings, meta, target):
    """Ad Manager / Bankier preview links need loading twice.

    The first request only sets the preview cookie; the creative is served on
    the next one. Loading once and reporting nothing found is a false
    negative — the page was never in the state being tested.
    """
    url = target["url"]
    page.goto(url, wait_until="load", timeout=60000)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))
    _log(meta, "first load (sets preview cookie)")
    time.sleep(2)

    page.goto(url, wait_until="load", timeout=60000)
    _log(meta, "second load (renders creative)")
    consent.accept(page, 1.5)
    _scroll(page, settings)
    _wait_for_impression(recorder, settings, meta, target.get("expected_id"))
    _click_creative(page, ctx, recorder, settings, meta, target.get("expected_id"))


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
        time.sleep(0.5)
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
    page.goto(url, wait_until="load", timeout=60000)
    meta["consent"] = consent.accept(page, settings.get("settle_after_consent", 3))
    time.sleep(3)

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
    budget = settings["patience"]
    per_click = max(12, budget // max(1, settings.get("max_link_clicks", 8)))

    for i, href in enumerate(links[:settings.get("max_link_clicks", 8)], 1):
        if not consent.alive(page):
            _log(meta, "page closed — stopping")
            break
        if recorder.has(kind=vendors.IMPRESSION, ident=expected):
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
            since = len(recorder.beacons)
            try:
                page.mouse.click(panel["x"], panel["y"])
            except Exception as e:
                _log(meta, f"    overlay click failed: {str(e)[:60]}")
            time.sleep(2)
            _confirm_click(recorder, meta, expected, since, source="overlay")
            if meta.get("click_result") == "confirmed":
                _log(meta, "    overlay fired")
                return

        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        consent.accept(page, 1.5)
        got = recorder.wait_for(
            lambda: recorder.has(kind=vendors.IMPRESSION, ident=expected),
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
            if not _click_overlay(page, ctx, recorder, settings, meta, expected):
                _click_creative(page, ctx, recorder, settings, meta, expected)
            return
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
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
    page.goto(target["url"], wait_until="load", timeout=60000)
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


def _await_video(page, recorder, expected_id, budget):
    """Wait for a spot to start, keeping the tab alive. -> what started.

    Returns "expected", "other" or None. Stopping on *any* serving impression
    rather than only the expected one matters more than it looks: instream is
    routinely trafficked as two spots in rotation, and waiting out the full
    budget for the 30s creative while the 15s one played and finished left
    the click landing on an empty player 160s later.
    """
    deadline = time.time() + budget
    while True:
        served = _serving_impressions(recorder)
        if expected_id and expected_id in served:
            return "expected"
        if served:
            return "other"
        if time.time() >= deadline:
            return None
        _keep_active(page)
        time.sleep(1.0)


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
    page.goto(target["url"], wait_until="load", timeout=60000)
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
    started = _await_video(page, recorder, expected_id, grace)
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
                               max(settings["patience"] - grace, 10))

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


# Strategies that cannot run in a headless browser. "watch" hands the window
# to a person, and "video" fronts the tab on purpose: a player whose tab
# Chrome considers occluded defers its pre-roll for minutes.
NEEDS_WINDOW = {"watch", "video"}

_STRATEGIES = {
    "load": load,
    "gam_preview": gam_preview,
    "navigation_click": navigation_click,
    "watch": watch,
    "video": video,
}
