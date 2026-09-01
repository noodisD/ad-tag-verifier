# ad-tag-verifier

Browser-automation scripts that answer a question ad operations normally
answers by hand: *is the right creative actually serving on a publisher page,
and does the click actually track?*

72 scripts, ~11,300 lines of Python, built up over several months verifying
Adform and Google CM360/DV360 tag delivery across ~20 Polish publisher
properties (Gazeta.pl, Agora, Interia, WP, Eska, Mamadu, NTO, ZPR, RASP,
PushAd and others) on behalf of advertisers spanning retail, banking and fuel
retail — referred to below by sector rather than name.

## What it does

Each script loads a live campaign preview URL in a real browser (Playwright),
clears the site's consent wall, waits out lazy-loaded ad slots, then scans
**every frame's full DOM plus the network layer** for impression beacons
(Adform `bn=`, CM360/DoubleClick creative and click-tracking requests) and
reports a pass/fail verdict per placement — separating the campaign's own
creative pixels from unrelated article-level ad noise.

Recurring techniques across the suite:

- **Consent handling**, layered: a JS pass matching Polish accept-button
  phrasing (`Akceptuję`, `Akceptuj wszystkie`) with CSS-selector fallbacks for
  common CMPs (OneTrust and friends) underneath.
- **Cross-frame DOM scanning** — the ad slot rendering the beacon is very
  often not the top-level frame, so verification walks `page.frames` rather
  than trusting the outer document.
- **Network interception** (57 of the scripts) — hooking `page.on("request")`
  to catch beacons that never leave a DOM trace, with per-request timestamps
  relative to page load.
- **Mobile emulation** (26 scripts) — viewport, device scale and touch, to
  catch desktop/mobile serving differences.
- **Spreadsheet-driven bulk runs** (9 scripts) — reading placement lists
  straight off a campaign trafficking sheet with pandas instead of a
  hand-maintained URL list.

## On the redacted IDs and client names

This is real client-campaign tooling, made public after the fact. Every
Adform `bn=` value, Google `iu=` placement ID, DFP `lineItemId`, and
`creativeId` in these scripts has been replaced with a placeholder number —
those values are campaign-specific and were only ever meaningful for the
specific run that produced them; they carry no signal once the campaign has
ended. Nothing about *how the verification works* depended on redacting them.

Advertiser names have been replaced with generic sector labels
(`RetailClient`, `BankClient`, `FuelClient`) in filenames, comments and URL
fragments, and local absolute paths (usernames, employer, Downloads
filenames carrying internal job codes) have been replaced with relative
placeholder paths. A couple of scripts (`verify_bts2026*.py`) embed the
client's macro-generated `wfName=` tracking string verbatim inside a
publisher tag URL — those substrings were substituted in place rather than
removed, since removing them would have broken the URL's structure.

Publisher domains and site structure are left as-is — that's public
information, not client-confidential, and it's the part that actually shows
what the tooling handles (Polish news/portal consent flows, ad-slot lazy
loading, iframe nesting).

To point a script at a real campaign, replace the placeholder IDs in its
`URLS` (or equivalent) list at the top of the file with the actual preview
URL and expected `bn=`/creative ID for that placement.

## Why this many scripts

This is a working toolkit accumulated script-by-script against real,
time-boxed verification requests — not a framework designed up front. That
shows in the duplication: consent-handling and DOM-scanning logic is
re-derived per script rather than factored into a shared module. Left as-is
deliberately, because it's an honest artifact of how the work actually
happened, not a retrofit.

## Requirements

```bash
pip install -r requirements.txt
playwright install chromium
```

## Running a script

```bash
python scripts/verify_gazeta_final.py
```

Each script edits the placement list at its own top, then writes a
timestamped log to a `.txt` file alongside itself (see the `Tee` class near
the top of most scripts) as well as stdout.

The pandas-driven scripts (`check_abt_zpr_agora.py`, `read_agora_tags.py`,
`read_cyber_tags.py`, `read_hvp_tags.py`, `read_retailclient_tags.py`,
`read_zpr_all.py`) read a trafficking-sheet export from `./data/` — that path
is a placeholder; point it at your own exported `.xlsx`/`.xls`.

## Layout

```
scripts/
  verify_*.py       per-publisher / per-campaign verification runs
  check_*.py        one-off checks (ad dimensions, click counts)
  diag_*.py         diagnostic scripts — dump every request matching a pattern
  read_*.py         tag readers — extract IDs from a live page or tag snippet
  retest_*.py       targeted re-runs against previously failed placements
  monitor_pudelek.py
  test_click_dv360.py
frontend/
  index.html        extraction UI + scan/select/match flow, self-contained
backend/
  app.py            Flask API: /discover (scan pages), /verify (self-check)
  verifier.py       the Playwright scan + check, generalized from scripts/
```

## Frontend — Tag ID Extractor

`frontend/index.html` is a single self-contained page (no build step, no
server) for the step that happens before any of the scripts above run:
pulling the platform and ID out of a tag someone pasted from an email, or out
of a trafficking-sheet export.

Open it directly in a browser — `frontend/index.html`, no server needed. Two
input modes:

- **Paste raw text** — drop in an email body, a Slack message, whatever.
  Every URL in the text is scanned; prose and broken line-wraps around it are
  ignored.
- **Upload a trafficking sheet** (`.xlsx`/`.xls`, parsed client-side via
  [SheetJS](https://sheetjs.com)) — every cell on every sheet is scanned, and
  each match reports back the sheet and cell it came from (e.g. `Sheet1!C14`),
  the same way the `read_*_tags.py` scripts do it with pandas.

Recognizes the same three platforms the scripts verify — Adform (`bn=`),
CM360 (`dc_trk_aid`, `dc_trk_cid`, the `N…/B…` site/placement pair), and
Google Ad Manager preview URLs (`iu`, `lineItemId`, `creativeId`,
`gdfp_req`) — and turns the results into a `URLS = [...]` list in the exact
tuple shape every `verify_*.py` script already expects, one click away on the
clipboard. Nothing is uploaded anywhere; parsing runs entirely in the
browser tab.

**A trafficking sheet and a pasted email combine, they don't replace each
other.** Upload the sheet, then paste the email (or the other order) — both
actions add to the same session. They're two different things: the sheet is
what a tag *should* be, and the email is a list of pages where it should
have been implemented. Those pages are usually bare preview links with no
tag ID of their own (`.../120x600_faul/`, or a publisher URL carrying the
creative name in a query param), so the extractor recognizes that shape too
and parses `{size, variant}` out of it.

## Backend — scanning live pages

Extraction never needs a server. Checking whether a tag is *actually
implemented* does: that means opening the page in a real browser, getting
past the consent wall, and watching what fires. `backend/` is a small Flask
API for that, and the frontend drives it in three steps:

**1 · Scan test pages.** Every test URL is opened for real and every ad tag
that fires is recorded — Adform, CM360, ABT Shield, DoubleVerify. Nothing is
compared at this stage and no expected value is sent; the page is simply the
source of truth for what is there. One scan per test URL, so the run is
bounded by how many tests you pasted, not by how many rows the sheet has.

**2 · Pick which tags matter.** The vendors actually seen across the scanned
pages become the filter — Adform and CM360 are the serving tags and are
selected by default; ABT Shield and DoubleVerify ride alongside as
measurement vendors and are opt-in, since not every campaign carries them.

**3 · Match against the sheet.** Only now is the trafficking sheet consulted:
each discovered ID is looked up in it. A selected vendor that never fired is
flagged `missing`; an ID that fired but isn't in the sheet is `not in sheet`;
and an ID that *is* in the sheet but under a row naming a different creative
is called out explicitly — that's the right slot running the wrong tag, which
is the failure this is really for.

Because discovery runs before any comparison, the tool reports what the page
does even with no sheet uploaded at all — the sheet only changes the verdict,
not the finding.

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
python app.py                    # http://localhost:8877
```

Then open `frontend/index.html` as before — the backend status dot in the
header switches from "not running" to "ready" once it detects the API, and
the Verify button lights up. Full detail, including why only Adform/CM360
rows are checkable and how the check avoids trivially confirming its own
input, is in `backend/README.md`.
