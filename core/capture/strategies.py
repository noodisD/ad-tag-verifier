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

    try:
        el.scroll_into_view_if_needed(timeout=5000)
        time.sleep(1)
        box = el.bounding_box() or box
    except Exception:
        pass

    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    vp = settings["viewport"]
    if not (0 < cx < vp["width"] and 0 < cy < vp["height"]):
        # Clicking a clamped fallback coordinate is how the wrong ad gets
        # clicked and reported as this campaign's. Refuse instead.
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
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]

    try:
        links = page.evaluate(
            """(host) => Array.from(document.querySelectorAll('a[href]'))
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
            try:
                loc.scroll_into_view_if_needed(timeout=4000)
            except Exception:
                pass
            with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                loc.click(timeout=8000)     # real click: CB checks isTrusted
        except Exception as e:
            _log(meta, f"    link click failed: {str(e)[:80]}")
            continue

        consent.accept(page, 1.5)
        got = recorder.wait_for(
            lambda: recorder.has(kind=vendors.IMPRESSION, ident=expected),
            per_click, settings.get("poll_interval", 0.5))
        if got:
            _log(meta, "    overlay fired")
            break
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            consent.accept(page, 1.5)
        except Exception:
            break

    _click_creative(page, ctx, recorder, settings, meta, expected)


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


_STRATEGIES = {
    "load": load,
    "gam_preview": gam_preview,
    "navigation_click": navigation_click,
    "watch": watch,
}
