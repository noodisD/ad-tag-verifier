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

_JS = """(phrases) => {
    const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    const els = document.querySelectorAll(
        "button, a[role=button], div[role=button], [class*=accept], [id*=accept]");
    for (const p of phrases) {
        for (const b of els) {
            const t = norm(b.innerText);
            if (t === p || t.startsWith(p)) {
                const r = b.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { b.click(); return b.innerText.trim(); }
            }
        }
    }
    return null;
}"""


def accept(page, settle=3.0):
    """Dismiss the consent wall. Returns the label clicked, or None.

    The wall is script-rendered after load, so this waits before looking:
    checking straight after goto reliably finds nothing.
    """
    time.sleep(settle)

    for target in [page] + list(page.frames):
        try:
            clicked = target.evaluate(_JS, PHRASES)
            if clicked:
                time.sleep(2)
                return clicked[:60]
        except Exception:
            pass

    for target in [page] + list(page.frames):
        for sel in SELECTORS:
            try:
                btn = target.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click()
                    time.sleep(2)
                    return f"selector:{sel}"
            except Exception:
                pass

    return None


def alive(page):
    """Whether the page still exists — watch mode hands the browser to a
    person, who may close it mid-run."""
    try:
        page.evaluate("1")
        return True
    except Exception:
        return False
