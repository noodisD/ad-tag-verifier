"""Getting past the consent wall.

Lifted from backend/verifier.py:click_consent, which had the important detail
already: match in-page after normalizing whitespace, because these labels
carry non-breaking spaces ("AKCEPTUJĘ I PRZECHODZĘ DO SERWISU") that a literal
Playwright text selector never matches.

Two additions: the phrase list covers more publishers, and failure is
reported rather than swallowed — a page left sitting behind a consent wall
fires no ad tags at all, and that reads as "nothing implemented" when the run
never actually got started.
"""

import time

# Longest / most specific first: WP's "accept and continue" has to win over a
# bare "akceptuję" prefix match, or the click lands on the wrong button.
PHRASES = [
    "akceptuję i przechodzę do serwisu",
    "akceptuj wszystkie i przejdź",
    "zaakceptuj i zamknij",
    "akceptuję wszystkie",
    "zaakceptuj wszystkie",
    "akceptuj wszystkie",
    "przejdź do serwisu",
    "zgadzam się",
    "accept all",
    "akceptuję",
    "akceptuj",
]

SELECTORS = [
    "#didomi-notice-agree-button",
    "#onetrust-accept-btn-handler",
    "[data-st='gdpr-accept']",
    ".rodo-popup-agree",
    ".fc-primary-button",
    "[data-cmp-exp='acceptAll']",
    "button.sp_choice_type_11",
    "button[class*='accept']",
]

# Deliberately not restricted to <button>. TVP's accept control is a bare
# `<div class="tvp-covl__ab">` — no role, no `accept` in the class, no id — so
# a selector list built from button-ish shapes walks straight past it and the
# run then reports "no tags" on a page that never got past the wall. Text is
# the only thing these controls reliably have in common, so match on text and
# use the box to tell a control from the container around it.
_FIND = r"""(phrases) => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const found = [];
    const walk = (root, depth) => {
        if (depth > 6) return;
        let els;
        try { els = root.querySelectorAll('*'); } catch (e) { return; }
        for (const e of els) {
            const t = norm(e.innerText || e.textContent);
            for (let i = 0; i < phrases.length; i++) {
                const p = phrases[i];
                // The label and little else: a wrapper holding the whole
                // policy text starts with the phrase too, and clicking that
                // hits nothing.
                if (!t.startsWith(p) || t.length > p.length + 12) continue;
                const r = e.getBoundingClientRect();
                if (r.width < 30 || r.height < 10 || r.width > 700 || r.height > 160) continue;
                if (r.bottom < 0 || r.top > (window.innerHeight || 0) + 2000) continue;
                found.push({rank: i, area: r.width * r.height,
                            x: Math.round(r.x + r.width / 2),
                            y: Math.round(r.y + r.height / 2),
                            label: (e.innerText || e.textContent || '').trim().slice(0, 60)});
                break;
            }
            if (e.shadowRoot) walk(e.shadowRoot, depth + 1);
        }
    };
    walk(document, 0);
    // Best phrase first, then the tightest box around it.
    found.sort((a, b) => a.rank - b.rank || a.area - b.area);
    return found.slice(0, 4);
}"""

# Whether any accept label is still on the page. A CMP that ignored the click
# leaves it there, and "clicked something" is not the same claim as "the wall
# is gone".
_STILL = r"""(phrases) => {
    const t = (document.body.innerText || '').replace(/\s+/g, ' ').toLowerCase();
    return phrases.some(p => t.includes(p));
}"""


def pause(page, seconds, slice_s=0.5):
    """Wait `seconds` while Playwright keeps delivering events.

    time.sleep() is not a wait as far as Playwright's sync API is concerned:
    nothing it sends is dispatched until the next call into it, so every
    request made while Python sleeps reaches the recorder (and the HAR clock)
    in one burst afterwards. Measured on dziennik.pl: a pixel that fired at
    13s was stamped 274s, because the run had spent the 260s in between
    asleep — and a wait that cannot see anything arrive cannot end on it.
    page.wait_for_timeout() waits in the driver and dispatches as it goes.

    Sliced, so a page that closes mid-wait (watch mode, a crashed tab) costs
    only the rest of the wait as a plain sleep, never an exception.
    """
    deadline = time.time() + seconds
    while True:
        left = deadline - time.time()
        if left <= 0:
            return
        try:
            page.wait_for_timeout(min(left, slice_s) * 1000)
        except Exception:
            time.sleep(max(0.0, deadline - time.time()))
            return


def live_frames(page):
    """The page's frames that can be asked something right now.

    A frame with no address yet (an ad iframe still being created) never answers
    `evaluate` in a visible browser, and the call has no timeout — the whole run
    sat there: money.pl hung for good in a headed window and took ten minutes of
    queued tests with it, while the same page took 13 seconds headless.
    """
    out = []
    for fr in page.frames:
        try:
            if fr.is_detached() or not fr.url:
                continue
        except Exception:
            continue
        out.append(fr)
    return out


def _click_top_frame(page):
    """One pass over the top frame's accept candidates. The label clicked, or None."""
    try:
        for cand in page.evaluate(_FIND, PHRASES):
            try:
                page.mouse.click(cand["x"], cand["y"])
            except Exception:
                continue
            pause(page, 2)
            if not still_up(page):
                return cand["label"][:60]
    except Exception:
        pass
    return None


# How long to keep looking for a wall that was not there at first look. A
# slower browser (a visible window, a busy machine) renders the CMP late;
# one pass at a fixed delay then finds nothing and the run carries on behind
# the wall — Onet mobile did exactly that in a headed run.
LATE_WALL_S = 6


def accept(page, settle=3.0):
    """Dismiss the consent wall. Returns the label clicked, or None.

    The wall is script-rendered after load, so this waits before looking:
    checking straight after goto reliably finds nothing.

    Clicks in the top frame go through the mouse rather than `element.click()`.
    A CMP is entitled to ignore a synthetic click — it carries
    `isTrusted=false` — and one that does leaves the page sitting behind the
    wall while the run reports consent as handled.
    """
    pause(page, settle)

    label = _click_top_frame(page)
    if label:
        return label

    # Sub-frame CMPs: the coordinates above are frame-relative and would land
    # in the wrong place, so these keep the in-page click.
    for frame in live_frames(page):
        if frame is page.main_frame:
            continue
        try:
            for cand in frame.evaluate(_FIND, PHRASES):
                frame.evaluate(
                    "(c) => { const el = document.elementFromPoint(c.x, c.y);"
                    "  if (el) el.click(); }", cand)
                pause(page, 2)
                if not still_up(page):
                    return cand["label"][:60]
        except Exception:
            pass

    for target in [page] + live_frames(page):
        for sel in SELECTORS:
            try:
                btn = target.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click()
                    pause(page, 2)
                    return f"selector:{sel}"
            except Exception:
                pass

    deadline = time.time() + LATE_WALL_S
    while time.time() < deadline:
        if still_up(page):
            label = _click_top_frame(page)
            if label:
                return label
        pause(page, 1)

    return None


def still_up(page):
    """Is an accept label still on the page?"""
    try:
        return bool(page.evaluate(_STILL, PHRASES))
    except Exception:
        return False


def alive(page):
    """Whether the page still exists — watch mode hands the browser to a
    person, who may close it mid-run."""
    try:
        page.evaluate("1")
        return True
    except Exception:
        return False
