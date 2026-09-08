"""Matching email labels to sheet rows. No network: the model is a stub.

What is pinned here is the division of labour — scoring decides what it can,
the model is only consulted on the rest, and neither is allowed to hand back
a confident answer that a size conflict contradicts.
"""
from core.ai import match

SHEET = [
    {"name": "Publisher_direct_300x250-Rectangle_CPC_PCC_Bkm-wiz", "expected_id": "90069306"},
    {"name": "Publisher_direct_300x600-HalfPage_CPC_PCC_Bkm-wiz", "expected_id": "90069307"},
    {"name": "Publisher_direct_750x200-DoubleBillboard_CPC_PCC_Bkm-wiz", "expected_id": "90069314"},
    {"name": "Publisher_direct_750x300-TrippleBillboard_CPC_PCC_Bkm-wiz", "expected_id": "90069316"},
]


class Stub:
    """Records what it was asked; answers however the test says."""
    def __init__(self, reply=None):
        self.reply, self.calls = reply, []

    def choose(self, label, candidates):
        self.calls.append((label, list(candidates)))
        return self.reply


def _one(label, **kw):
    return match.match([{"label": label, "url": "https://example.test/x"}], SHEET, **kw)[0]


def test_clear_label_is_matched_without_asking_the_model():
    stub = Stub()
    r = _one("300x250 Rectangle", model=stub)
    assert r["expected_id"] == "90069306"
    assert r["source"] == "score"
    assert r["needs_review"] is False
    assert stub.calls == [], "the model must not be consulted when scoring is sure"


def test_id_in_the_email_wins_outright():
    r = match.match(
        [{"label": "whatever", "url": "u", "explicit_id": "455256307"}], SHEET)[0]
    assert (r["expected_id"], r["source"], r["needs_review"]) == ("455256307", "explicit", False)


def test_model_is_asked_only_for_the_uncertain_tail_and_gets_a_shortlist():
    stub = Stub({"index": 0, "confidence": 0.8, "reason": "same format"})
    _one("double billboard wide", model=stub)
    assert len(stub.calls) == 1
    _label, candidates = stub.calls[0]
    assert 0 < len(candidates) <= 6, "the model gets a shortlist, not the whole sheet"


def test_a_model_match_still_goes_to_a_person():
    stub = Stub({"index": 2, "confidence": 0.95, "reason": "double billboard"})
    r = _one("double billboard wide", model=stub)
    if r["source"] == "model":
        assert r["needs_review"] is True, "a model match is a suggestion, never a fact"


def test_a_refusal_leaves_the_row_unmatched_rather_than_guessing():
    r = _one("double billboard wide", model=Stub({"index": None, "confidence": 0.0}))
    assert r["expected_id"] is None
    assert r["needs_review"] is True
    assert any("declined" in w for w in r["warnings"])


# The stale-export failure, in its two possible shapes: a plausible name
# carrying the wrong format. Neither may end up looking resolved.
CONFLICT = [{"name": "Publisher_direct_120x600-Skyscrapper_FIX", "expected_id": "90069246"}]
CONFLICT_LABEL = "Publisher direct 300x250 Rectangle"


def test_size_conflict_is_not_matched_at_all_without_a_model():
    r = match.match([{"label": CONFLICT_LABEL, "url": "u"}], CONFLICT)[0]
    assert r["expected_id"] is None
    assert r["needs_review"] is True


def test_size_conflict_proposed_by_the_model_is_flagged_and_held_back():
    stub = Stub({"index": 0, "confidence": 0.99, "reason": "looks like the same row"})
    r = match.match([{"label": CONFLICT_LABEL, "url": "u"}], CONFLICT, model=stub)[0]
    assert any("size disagrees" in w for w in r["warnings"]), r["warnings"]
    assert r["needs_review"] is True, "high model confidence must not override a size conflict"


def test_one_sheet_row_claimed_twice_is_flagged_on_both():
    rows = [{"name": "Publisher_direct_300x250-Rectangle_CPC", "expected_id": "1"}]
    res = match.match([{"label": "300x250 Rectangle", "url": "a"},
                       {"label": "300x250 Rectangle", "url": "b"}], rows)
    assert all(any("matched 2x" in w for w in r["warnings"]) for r in res)
    assert all(r["needs_review"] for r in res)


def test_nothing_resembling_the_label_is_admitted_not_forced():
    r = _one("completely unrelated text")
    assert r["expected_id"] is None and r["source"] == "none"


def test_no_key_means_no_model_rather_than_a_crash():
    import os
    saved = os.environ.pop("GEMINI_API_KEY", None)
    try:
        assert match.default_model() is None
    finally:
        if saved:
            os.environ["GEMINI_API_KEY"] = saved


def test_mobile_viewport_is_inferred_from_label_and_size():
    assert match.guess_viewport("interstitial 320x480") == "mobile"
    assert match.guess_viewport("750x300 TrippleBillboard") == "desktop"


# ── the model's reply is untrusted input ─────────────────────────────────

def test_string_confidence_is_coerced_not_crashed_on():
    """Seen in practice: {"index": 2, "confidence": "0.9"}. Passing that
    straight through raised TypeError in round()."""
    # index 0 is the top of the *shortlist* — ranked by score, not sheet order.
    r = _one("double billboard wide",
             model=Stub({"index": "0", "confidence": "0.9", "reason": "same format"}))
    assert isinstance(r["confidence"], float)
    assert r["confidence"] == 0.9
    assert r["expected_id"] == "90069314", "top-ranked candidate is the 750x200 row"


def test_a_nonsense_reply_is_treated_as_a_refusal():
    for reply in ({"index": 99, "confidence": 1.0},      # out of range
                  {"index": -1, "confidence": 1.0},
                  {"index": True, "confidence": 1.0},    # bool is not a position
                  {"index": "abc"},
                  {"confidence": 0.9},                   # no index at all
                  "not a dict", None, []):
        r = _one("double billboard wide", model=Stub(reply))
        assert r["expected_id"] is None, f"accepted junk: {reply!r}"
        assert r["needs_review"] is True


def test_confidence_is_clamped_to_a_sane_range():
    r = _one("double billboard wide", model=Stub({"index": 2, "confidence": 7.5}))
    assert 0.0 <= r["confidence"] <= 1.0


def test_a_model_that_raises_does_not_take_the_run_down():
    class Boom:
        def choose(self, *a):
            raise RuntimeError("network died")
    r = _one("double billboard wide", model=Boom())
    assert r["expected_id"] is None and r["needs_review"] is True
