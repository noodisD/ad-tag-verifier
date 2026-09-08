# ad-tag-verifier

Browser-automation scripts that answer a question ad operations normally
answers by hand: *is the right creative actually serving on a publisher page,
and does the click actually track?*

72 scripts, ~11,300 lines of Python, built up over several months verifying
Adform and Google CM360/DV360 tag delivery across ~20 Polish publisher
properties (Gazeta.pl, Agora, Interia, WP, Eska, Mamadu, NTO, ZPR, RASP,
PushAd and others) on behalf of advertisers spanning retail, banking and fuel
retail — referred to below by sector rather than name.

Those scripts are kept as history. The working tool is now `core/`, which
distils them into two halves that never touch each other: a browser that
gathers evidence and decides nothing, and an analyzer that reads that evidence
and never opens a browser. `frontend/` and `backend/` drive it.

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

One deliberate exception: `frontend/index.html` ships three real
advertiser names in the "advertiser" suggestion list. That field is what tells
the vision fallback whose creative to click, and the page is a tool someone
uses daily rather than a sample — typing the client name every run to keep a
README claim tidy would be the wrong trade. The names are the only place they
appear outside `scripts/`.

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

## Running one of the historical scripts

The scripts in `scripts/` still run, and are the record of how this grew.
New work goes through `core/`.

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
core/                 the engine
  profiles.yaml       per-site behaviour — adding a publisher is an entry, not code
  profiles.py         resolves a URL to merged settings
  capture/            one session -> one artifact (run.har + meta.json + screenshot)
    strategies.py     load / gam_preview / navigation_click / watch
    consent.py        getting past the consent wall
  analyze/            artifact -> verdict. No browser.
    vendors.py        what each vendor's beacons look like, split impression/click
  ai/                 the two places a model earns its keep (see below)
  report/html.py      one self-contained file, screenshots embedded
  tests/              fast, browser-free
  artifacts/          run output — gitignored, carries real campaign data
backend/
  app.py              Flask API: /discover, /verify, /match, /watch/<id>/done
  engine.py           bridge from the HTTP shape to core/
  verifier.py         the original scan, superseded by core/ and kept for reference
frontend/
  index.html          single self-contained page, no build step
scripts/              126 -> 72 one-off runs, the honest record of how this grew
```

## The engine — capture, then analyze

The browser produces evidence and decides nothing. Verdicts come from reading
that evidence afterwards, which buys three things the per-script approach
could not have:

- **A wrong detection rule costs one re-read, not a re-run.** Working out that
  `securepubads.g.doubleclick.net` is Ad Manager's own infrastructure rather
  than a CM360 beacon used to mean re-driving every page. Capture takes ~30-150s
  on a live publisher page; re-analysing the stored artifact takes under a
  second.
- **Evidence survives the run.** A verdict printed to stdout is not something
  you can send a publisher who disagrees. Every run leaves a HAR they can open
  in their own devtools.
- **Regression tests exist.** There is no way to test against a live page.
  There is one against a stored HAR, and `core/tests/` pins every
  classification rule that has been got wrong.

`profiles.yaml` holds the per-site knowledge that used to be spread across
`scripts/`. Two kinds of entry, merged in file order:

- **How long a publisher's stack really takes.** dziennik.pl serves its
  impression at 96.9s; a 60s budget reports "no tags" on a page that is fine.
- **How the page has to be driven.** A GAM preview needs two loads — the first
  only sets the cookie. WP's Commercial Break overlay appears only on a real
  in-page navigation, so the run clicks an article link. RASP's `#adbeta=`
  names the slot in the URL fragment and reads it at load, so it must be
  present on the first navigation.

Every vendor is split by impression and click. Matching `doubleclick.net/ddm/track`
as one bucket cannot answer the question the tool exists for — *does the click
track too?*

### watch — where automation is not trusted

On pages carrying several same-size slots, automated clicking repeatedly
clicked *other advertisers'* creatives and reported them as the campaign's.
Four successive targeting methods — by size, by frame content, by the frame
that fired the impression, and clicking within a second of it — all failed the
same way, because the slot can refresh between the impression and the click.

So `watch` hands the browser to a person: they click, the tool records. It is
a deliberate limit, not a gap. A person clicks correctly in seconds; capturing
the evidence is the part worth automating.

## The AI layer

Narrow by design, and confined to two jobs. **Neither decides whether a tag
fired** — that stays a deterministic match over the HAR, because a verdict has
to be evidence you can send a publisher.

- **`core/ai/match.py`** pairs the test URLs named in an email with the rows of
  a trafficking sheet. Name scoring settles the clear cases outright and the
  model is not consulted at all; only what scoring cannot settle is put to it,
  as a ranked shortlist, and it may decline. A size conflict is never reported
  as resolved whatever the confidence says — that is the shape of the stale-export
  failure, where the same tag ID was described as one format in a morning
  export and another in the afternoon's.
- **`core/ai/creative_click.py`** is a fallback for clicking. Deterministic
  targeting is always tried first and is exact when it works; it finds nothing
  on screenings and wallpapers, where the run would otherwise log "click
  skipped" and the placement would look click-less although nothing had been
  attempted. The model points at the creative on a screenshot, and the click
  counts **only if the beacon that follows carries the expected ID**. A click
  landing on a competitor's creative produces somebody else's beacon and is
  recorded as exactly that — a wrong guess is discarded, not reported.

Credentials come from the environment: `GEMINI_API_KEY` for AI Studio, or
`GOOGLE_APPLICATION_CREDENTIALS` for Vertex AI. With neither set the fallback
is simply absent and more rows are left for a person.

## Frontend

`frontend/index.html` is a single self-contained page — no build step. Open it
directly, or serve the folder over HTTP if a corporate proxy blocks the
SheetJS CDN (the page says so rather than failing silently).

The flow follows what actually arrives in the inbox:

**Read the email.** Publishers and creative agencies send a creative name and,
on the line below it, a link — a DV360 preview, a WP `wfName=` page, a RASP
`#adbeta=` slot. The name is carried onto the link, so twenty-two rows do not
all read "preview". Formats are read wherever they are stated: `flexWidth`/
`flexHeight` on DV360 links, `970_300` where WP writes it with an underscore.

**Upload the trafficking sheet.** A sheet states what is *booked*; the email
says where to look. They combine into one session, in either order, and only
the email contributes pages to scan — a sheet's click-through column is the
advertiser's landing page, not a test.

**1 · Scan.** Every test URL is opened for real and every tag that fires is
recorded. Nothing is compared yet.

**2 · Which tags to check.** The vendors actually seen become the filter.
Adform and CM360 are the serving tags; ABT Shield and DoubleVerify ride
alongside as measurement and are opt-in.

**3 · Match.** Each discovered ID is looked up in the sheet. The ID is the
identity — sizes and creative names are never used to decide *which* tag
something is. What is checked, when both sides state it, is whether the format
the email gave a creative agrees with the format the sheet books that ID under.

Impression and click are reported separately, and "not tested" is distinct
from "did not fire": a click the run never managed to attempt says nothing
about the tag, and reporting it as missing raises a defect against a placement
that may be correct.

## Backend

```bash
cd backend && python app.py          # http://localhost:8877
```

Then open the frontend. The status dot in the header goes green once it sees
the API; click it to re-check if you started the backend afterwards.

Endpoints: `/discover` (scan pages), `/verify` (check against expected IDs),
`/match` (pair email to sheet), `/watch/<run_id>/done` (the operator says they
have finished clicking in watch mode). Runs are backgrounded and polled; a run
that cannot start — usually because `playwright install chromium` was never
run — reports that rather than finishing quietly with every row pending.

## The CLI

Everything the API does is also a command, and the analyzer runs without a
browser at all:

```bash
python -m core.cli profile "<url>"                 # how would this be driven?
python -m core.cli capture --jobs jobs.json --advertiser "SomeBrand"
python -m core.cli analyze core/artifacts/<run>    # re-read, no browser
python -m core.cli report  core/artifacts/<run>
python -m pytest core/tests backend/tests -q
```

`profile` opens no browser — it is the cheapest way to confirm a new
`profiles.yaml` entry does what you meant.

## Artifacts are not committed

A run artifact carries real campaign IDs and publisher URLs. HARs are recorded
in `minimal` mode, which omits response bodies and cookies, but they are still
campaign data — `core/artifacts/` is gitignored, as is `.env`.
