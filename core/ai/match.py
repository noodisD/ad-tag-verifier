"""Pair the test URLs named in a campaign email with the rows of a
trafficking sheet.

This is the one step in the pipeline that is genuinely linguistic. An email
says "wide:", "navik mobile:", or a size in a heading; the sheet says
`Publisher_direct_750x200-DoubleBillboard_CPC_…`. Labels arrive in two
languages, inside markdown tables, wrapped by a mail client. Regular
expressions get most of it and then break on the tail.

The split of responsibility here is deliberate:

- **Scoring decides whenever it can.** It is deterministic, explainable and
  free, and it is right about the large majority of rows.
- **A model is asked only about what scoring could not settle**, and it is
  allowed to answer "I don't know".
- **Nothing here decides whether a tag fired.** That verdict stays with
  `core/analyze`, reading a HAR. A model's opinion is not evidence you can
  send a publisher.

Anything still unresolved is returned with `needs_review` set. A confident
wrong answer is worse than an admitted gap: this is exactly the step where
testing once ran against a stale export in which the same tag ID was
described as a different format, and everything downstream inherited it.
"""

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher

SIZE_RE = re.compile(r"(\d{2,4})\s*[xX]\s*(\d{2,4})")

# Above this, the deterministic score is taken at face value.
CONFIDENT = 0.70
# Below this there is no usable deterministic claim at all.
FLOOR = 0.45

MOBILE_HINTS = ("mobile", "navik", "mob", "smartfon", "phone", "interstitial")
MOBILE_SIZES = {(300, 250), (300, 600), (320, 480), (320, 100), (320, 50),
                (336, 280), (336, 480), (480, 320), (600, 400), (600, 200),
                (250, 250), (300, 50)}

# Creative variants that campaigns split on. A shared one is real evidence of
# a pair; a contradicting one is real evidence against.
VARIANT_TOKENS = ("oferta", "terminal", "topa", "mlody", "młody", "ladies",
                  "family", "wide", "navik", "rtg", "ogolna", "ogólna")


def extract_size(text):
    m = SIZE_RE.search(text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def guess_viewport(label, url=""):
    hay = f"{label} {url}".lower()
    if any(h in hay for h in MOBILE_HINTS):
        return "mobile"
    size = extract_size(label)
    if size:
        if size in MOBILE_SIZES:
            return "mobile"
        if size[0] >= 700:
            return "desktop"
    return "desktop"


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def score(label, row_name):
    """How well an email label matches a sheet row name, 0..1.5.

    Size agreement dominates on purpose: two rows of the same campaign often
    read almost identically apart from the format, and the format is the part
    that must not be got wrong.
    """
    a, b = _norm(label), _norm(row_name)
    if not a or not b:
        return 0.0

    base = 0.9 if (a in b or b in a) else SequenceMatcher(None, a, b).ratio()

    sa, sb = extract_size(label), extract_size(row_name)
    if sa and sb:
        base = base + 0.25 if sa == sb else base - 0.35

    low_l, low_r = (label or "").lower(), (row_name or "").lower()
    for token in VARIANT_TOKENS:
        in_l, in_r = token in low_l, token in low_r
        if in_l and in_r:
            base += 0.12
        elif in_l != in_r:
            base -= 0.06

    return max(0.0, min(base, 1.5))


def _entry(item):
    return {
        "label": item.get("label", ""),
        "url": item.get("url", ""),
        "viewport": guess_viewport(item.get("label", ""), item.get("url", "")),
        "expected_id": None,
        "matched_row": None,
        "confidence": 0.0,
        "source": None,          # explicit | score | model | none
        "needs_review": True,
        "warnings": [],
    }


def _apply(entry, row, confidence, source):
    entry.update({
        "expected_id": row.get("expected_id") or row.get("id"),
        "matched_row": row.get("name"),
        "confidence": round(confidence, 2),
        "source": source,
    })
    size_l = extract_size(entry["label"])
    size_r = extract_size(row.get("name", ""))
    if size_l and size_r and size_l != size_r:
        entry["warnings"].append(
            f"size disagrees: label {size_l[0]}x{size_l[1]} vs sheet {size_r[0]}x{size_r[1]}")
    # A size conflict is never "resolved", whatever the score says — that is
    # the shape the stale-export incident took.
    entry["needs_review"] = bool(entry["warnings"]) or confidence < CONFIDENT
    return entry


def match(email_items, sheet_rows, model=None, threshold=FLOOR):
    """-> one entry per email item.

    email_items: [{"label": str, "url": str, "explicit_id": str|None}]
    sheet_rows:  [{"name": str, "expected_id": str}]
    model:       optional object with .choose(label, candidates) -> dict
    """
    used = {}
    out = []

    for item in email_items:
        entry = _entry(item)

        # An ID written out in the email beats any similarity score.
        if item.get("explicit_id"):
            entry.update({"expected_id": item["explicit_id"], "confidence": 1.0,
                          "source": "explicit", "matched_row": "(id given in email)",
                          "needs_review": False})
            out.append(entry)
            continue

        ranked = sorted(
            ((score(entry["label"], r.get("name", "")), i) for i, r in enumerate(sheet_rows)),
            reverse=True)
        best_score, best_i = ranked[0] if ranked else (0.0, None)

        if best_i is not None and best_score >= CONFIDENT:
            _apply(entry, sheet_rows[best_i], best_score, "score")
            used.setdefault(best_i, []).append(entry)

        elif model is not None and sheet_rows:
            # Everything scoring could not settle, including labels that score
            # below the deterministic floor — those are precisely the ones the
            # model is here for. ("double billboard wide" against
            # `…750x200-DoubleBillboard…` scores 0.44: too low to assert, far
            # too plausible to discard.) The model gets a ranked shortlist
            # rather than the whole sheet: cheaper, and much harder to answer
            # carelessly.
            shortlist = [sheet_rows[i] for _s, i in ranked[:6]]
            verdict = _ask(model, entry["label"], shortlist)
            if verdict and verdict.get("index") is not None:
                _apply(entry, shortlist[verdict["index"]],
                       verdict.get("confidence", 0.0), "model")
                if verdict.get("reason"):
                    entry["warnings"].append("model: " + verdict["reason"][:120])
                entry["needs_review"] = True   # a model match is a suggestion, never a fact
            else:
                entry["warnings"].append("model declined to match")
                entry["source"] = "none"

        elif best_i is not None and best_score >= threshold:
            _apply(entry, sheet_rows[best_i], best_score, "score")
            entry["warnings"].append("weak match — confirm before running")
            used.setdefault(best_i, []).append(entry)

        else:
            entry["warnings"].append("no row in the sheet resembles this label")
            entry["source"] = "none"

        out.append(entry)

    for i, entries in used.items():
        if len(entries) > 1:
            for e in entries:
                e["warnings"].append(f"sheet row matched {len(entries)}x: {sheet_rows[i].get('name')}")
                e["needs_review"] = True

    return out


def _ask(model, label, shortlist):
    """Consult the model and normalise what comes back.

    Model output is untrusted input: the shape is requested, not guaranteed.
    A returned index has to be a real position in the shortlist, and
    confidence has arrived as a string (`"0.9"`) often enough that coercing it
    is not defensive programming but a plain requirement.
    """
    try:
        v = model.choose(label, [r.get("name", "") for r in shortlist])
    except Exception:
        return None
    if not isinstance(v, dict):
        return None

    idx = v.get("index")
    if isinstance(idx, str) and idx.strip().lstrip("-").isdigit():
        idx = int(idx)
    if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(shortlist):
        return None

    try:
        confidence = float(v.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    reason = v.get("reason")
    return {"index": idx,
            "confidence": max(0.0, min(confidence, 1.0)),
            "reason": reason if isinstance(reason, str) else ""}


# ── the model, kept at arm's length ──────────────────────────────────────

PROMPT = """You are matching one line from a media-campaign email to the row \
of a trafficking sheet that describes the same ad placement.

Email label:
{label}

Candidate rows:
{candidates}

Rules:
- The ad format (e.g. 300x250, 750x200) must agree. If the label names a
  format and no candidate shares it, refuse.
- Creative variants in the names (audience, offer, retargeting) must not
  contradict each other.
- Refuse if you are not sure. A wrong match is far worse than no match.

Reply with JSON only: {{"index": <0-based index or null>, \
"confidence": <0..1>, "reason": "<short>"}}"""


class GeminiMatcher:
    """Minimal REST client, speaking either of the two ways Gemini is reached.

    Deliberately not a hard dependency of the package: everything above works
    without it, just with more rows left for a person to settle.

    Credentials are read from the environment and never leave the server —
    they must not reach `frontend/index.html`, which is a static file served
    from a public repo.

    - **AI Studio** — `GEMINI_API_KEY`. No extra packages.
    - **Vertex AI** — `GOOGLE_APPLICATION_CREDENTIALS` pointing at a service
      account file, plus `google-auth`. Used when both are present, since a
      service account is the form corporate projects usually issue.

    Only the path to the credentials file is ever configured; its contents are
    not copied anywhere, least of all into this repo.
    """

    STUDIO = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent")
    VERTEX = ("https://{loc}-aiplatform.googleapis.com/v1/projects/{project}"
              "/locations/{loc}/publishers/google/models/{model}:generateContent")
    SCOPE = "https://www.googleapis.com/auth/cloud-platform"

    def __init__(self, api_key=None, model=None, timeout=25,
                 credentials_path=None, location=None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        # Vertex only serves what a given project has available; asking for a
        # model it does not carry is a 404 that reads like "no access".
        # Override with GEMINI_MODEL when a project offers something else.
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.location = location or os.environ.get("GEMINI_LOCATION", "us-central1")
        self.timeout = timeout
        self._creds_path = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        self._creds = None
        # Why the last generate() came back empty, when it was the call that
        # failed rather than the model declining. None after a real answer.
        self.last_error = None

    # ── auth ─────────────────────────────────────────────────────────────

    def _service_account(self):
        """Cached credentials, or None if unusable. Never raises: a matcher
        that cannot authenticate simply leaves rows for a person."""
        if self._creds is not None:
            return self._creds
        if not self._creds_path or not os.path.exists(self._creds_path):
            return None
        try:
            from google.oauth2 import service_account
            self._creds = service_account.Credentials.from_service_account_file(
                self._creds_path, scopes=[self.SCOPE])
        except Exception:
            return None
        return self._creds

    def _bearer(self):
        creds = self._service_account()
        if creds is None:
            return None
        try:
            import google.auth.transport.requests as transport
            if not creds.valid:
                creds.refresh(transport.Request())
            return creds.token
        except Exception:
            return None

    @property
    def mode(self):
        if self._service_account() is not None:
            return "vertex"
        if self.api_key:
            return "studio"
        return None

    @property
    def available(self):
        return self.mode is not None

    # ── request ──────────────────────────────────────────────────────────

    def _endpoint_and_headers(self):
        if self.mode == "vertex":
            token = self._bearer()
            if not token:
                return None, None
            creds = self._service_account()
            url = self.VERTEX.format(loc=self.location, project=creds.project_id,
                                     model=self.model)
            return url, {"Content-Type": "application/json",
                         "Authorization": "Bearer " + token}
        if self.mode == "studio":
            return (self.STUDIO.format(model=self.model) + "?key=" + self.api_key,
                    {"Content-Type": "application/json"})
        return None, None

    def choose(self, label, candidates):
        listing = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates))
        text = self.generate([{"role": "user", "parts": [
            {"text": PROMPT.format(label=label, candidates=listing)}]}])
        if not text:
            return None
        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return None

    RETRY_STATUS = (429, 500, 503)
    MAX_RETRIES = 2

    def generate(self, contents):
        """One answer; -> the model's reply text, or None.

        Split out of `choose` so the vision fallback in `ai.creative_click`
        can send an image through this same client and these same
        credentials, rather than opening a second route to the model.

        A rate limit or a passing server error is retried, but only inside
        `timeout` as a whole: the vision step budgets one call at that length
        (strategies.VISION_LOOK_S), and ten runs at once are exactly when the
        quota answers 429. A timeout is not retried — it already spent the
        budget. When the answer is None because the call failed, last_error
        says how; until now a 429 read as "the model looked and found nothing".
        """
        self.last_error = None
        url, headers = self._endpoint_and_headers()
        if not url:
            return None

        body = {"contents": contents,
                "generationConfig": {"temperature": 0,
                                     "responseMimeType": "application/json"}}
        data = json.dumps(body).encode("utf-8")
        deadline = time.monotonic() + self.timeout
        attempt = 0
        while True:
            left = deadline - time.monotonic()
            if left <= 0.5:
                self.last_error = self.last_error or "out of time"
                return None
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=left) as r:
                    payload = json.load(r)
                self.last_error = None       # a retry that got through
                break
            except urllib.error.HTTPError as e:
                self.last_error = ("rate limited" if e.code == 429 else "model call failed") \
                    + f" (HTTP {e.code})"
                if e.code not in self.RETRY_STATUS or attempt >= self.MAX_RETRIES:
                    return None
                wait = _retry_after(e)
                if wait is None:
                    wait = min(2 ** attempt, 4) + random.uniform(0, 0.5)
                if wait >= deadline - time.monotonic() - 0.5:
                    return None              # no time left for another try
                time.sleep(wait)
                attempt += 1
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
                self.last_error = f"{type(e).__name__}: {str(e)[:80]}"
                return None

        try:
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None


def _retry_after(err):
    """Seconds the server asked us to wait, if it said so in seconds."""
    try:
        return max(0.0, float(err.headers.get("Retry-After")))
    except (AttributeError, TypeError, ValueError):
        return None


def default_model():
    """The configured matcher, or None when nothing is configured — in which
    case uncertain rows simply stay uncertain."""
    m = GeminiMatcher()
    return m if m.available else None
