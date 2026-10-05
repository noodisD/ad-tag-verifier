"""Ask a model where the creative is, then click it — and only believe the
result if the beacon agrees.

`strategies._creative_frame` identifies the creative deterministically: the
frame that fired the impression, or an `<a>` whose href is the click tracker.
That is exact when it works, and it should always be tried first. It finds
nothing on the formats that are neither — screenings and wallpapers painted
into the page, overlays whose click URL is assembled in JS at click time. On
those the run logs "click skipped" and the placement looks click-less when
nobody ever tried.

This is the fallback for that case. Two rules keep it from repeating the
failure that made automated clicking untrustworthy here in the first place —
four successive targeting methods that clicked *other advertisers'* creatives
and reported them as the campaign's:

1. **The model points, it does not conclude.** It returns a region of a
   screenshot. Whether a tag fired is still decided by reading the network.
2. **A click is only believed if the beacon agrees.** After clicking we look
   for a click beacon carrying the expected id. Anything else — no beacon, or
   one belonging to a different advertiser — is reported as untested, never
   as a pass. A wrong click becomes harmless instead of a false verdict.

Borrowed from UXAgent's executor: locate immediately before acting rather
than reusing an earlier observation (its `_reparse`), and recover from an
intercepted click by centring the target and retrying. Its parser itself is
no use here — it blacklists `iframe`, which is where creatives live.
"""

import base64
import json

from core.analyze import vendors

PROMPT = """You are looking at a screenshot of a publisher's web page that is \
running an advertising campaign.

Find the advertising creative for: {advertiser}

The page may carry several ads from different advertisers. Return only the one \
matching the advertiser above. Ignore navigation, articles, cookie banners and \
any other advertiser's creative.

The screenshot is {width} by {height} pixels.

Reply with JSON only:
{{"found": true|false, "x": <left>, "y": <top>, "w": <width>, "h": <height>, \
"confidence": <0..1>, "reason": "<short>"}}

Refuse with {{"found": false}} if you cannot see that advertiser's creative, or \
if you are not sure which of several ads is theirs. A wrong location makes the \
tool click a competitor's ad, which is far worse than not clicking at all."""


def locate(model, screenshot_png, advertiser, viewport, why=None):
    """-> {"x","y","w","h","confidence","reason"} or None.

    `screenshot_png` is raw bytes of the current viewport. `why`, when given a
    dict, is filled with what happened when the answer is None — the call
    failed, or the model answered and the answer was refused — because "could
    not locate" is otherwise the same line for a model that looked and a model
    that never got to.
    """
    why = why if why is not None else {}
    if model is None or not advertiser:
        return None
    try:
        reply = model.look(
            PROMPT.format(advertiser=advertiser,
                          width=viewport["width"], height=viewport["height"]),
            screenshot_png)
    except Exception as e:
        why["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return None
    box = _sane_box(reply, viewport)
    if box is None:
        why["reply"] = "no usable answer" if reply is None else str(reply)[:160]
    return box


def _sane_box(reply, viewport):
    """Validate the model's answer against the viewport it was shown.

    Model output is untrusted input: coordinates arrive as strings, as
    fractions of the viewport, or simply wrong. A box that is off-screen or
    the size of the whole page is not a creative, and clicking its centre
    lands on whatever happens to be there.
    """
    if not isinstance(reply, dict) or not reply.get("found"):
        return None

    def num(key):
        try:
            return float(reply.get(key))
        except (TypeError, ValueError):
            return None

    x, y, w, h = num("x"), num("y"), num("w"), num("h")
    if None in (x, y, w, h) or w <= 0 or h <= 0:
        return None

    vw, vh = viewport["width"], viewport["height"]
    if x < 0 or y < 0 or x + w > vw + 2 or y + h > vh + 2:
        return None
    # An "ad" covering most of the page is the page, not an ad.
    if w * h > 0.8 * vw * vh:
        return None
    if w < 30 or h < 20:
        return None

    try:
        confidence = float(reply.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = reply.get("reason")
    return {"x": x, "y": y, "w": w, "h": h,
            "confidence": max(0.0, min(confidence, 1.0)),
            "reason": reason if isinstance(reason, str) else ""}


def click_confirmed(recorder, expected_id, since_index):
    """Did the click produce the campaign's own click beacon?

    -> ("confirmed", id) | ("other_advertiser", id) | ("unattributed", id)
       | ("none", None)

    `since_index` is len(recorder.beacons) taken immediately before clicking,
    so an earlier click on the same page cannot be counted twice.
    """
    fresh = recorder.beacons[since_index:]
    # Only the serving vendors get a say in *whose* click this was. ABT
    # Shield's click pixel carries a fixed order id — 237250412 on every campaign of theirs
    # campaign — and reading that as an advertiser id turned a click that
    # landed correctly on `?bn=90116857` into "the slot is carrying another
    # advertiser". Measurement rides along; it does not identify anyone.
    clicks = [b for b in fresh
              if b.get("kind") == "click" and b.get("evidence") == "fired"
              and b.get("vendor") in vendors.SERVING_VENDORS]
    if not clicks:
        return "none", None
    # One id, or the set of ids a sheet books when the page never said which of
    # them it was serving: the click then has to carry one of those.
    wanted = {expected_id} if isinstance(expected_id, str) else set(expected_id or ())
    if wanted:
        for b in clicks:
            if b.get("id") in wanted:
                return "confirmed", b["id"]
        # A click tracked, but for somebody else — the slot was refreshed, or
        # the model pointed at a competitor. Worth surfacing on its own: it
        # says something real about the slot, and it is not this campaign's
        # click working.
        return "other_advertiser", clicks[0].get("id")
    # Nothing was expected, so nothing can be credited. Measured on a moto.pl
    # preview that never rendered the campaign's creative: the run clicked
    # what was in the slot, a CM360 click tracked, and it was reported as
    # "click confirmed" — for SkyShowtime, whose landing page it opened.
    return "unattributed", clicks[0].get("id")


class VisionMatcher:
    """The `look` half of the model interface, alongside ai.match's `choose`.

    Kept in the same shape so one configured client serves both, and so a
    deployment with no model simply loses the fallback rather than breaking.
    """

    def __init__(self, matcher):
        self._m = matcher      # an ai.match.GeminiMatcher

    @property
    def available(self):
        return self._m is not None and self._m.available

    def look(self, prompt, screenshot_png):
        if not self.available:
            return None
        image = {"inlineData": {"mimeType": "image/png",
                                "data": base64.b64encode(screenshot_png).decode("ascii")}}
        payload = self._m.generate(
            [{"role": "user", "parts": [{"text": prompt}, image]}])
        if not payload:
            return None
        try:
            return json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return None
