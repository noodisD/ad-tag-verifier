# backend

Local Flask API that gives the frontend's "Verify" button something to call.
Runs entirely on your machine — nothing about the frontend requires this to
be running; extraction (paste, upload, copy-as-Python-list) works with zero
backend at all. This only powers the optional live check: does the ID a tag
URL carries actually fire when the page loads.

## Setup

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
python app.py
```

Serves the API on `http://localhost:8877`. Open `../frontend/index.html`
directly in a browser (no server needed for the page itself) — once this is
running, its "Verify" button lights up.

## Parallel runs

Targets run `concurrency` at a time — 10 unless the request or
`TAGVERIFIER_CONCURRENCY` says otherwise, at most 20 across every run in the
process. The page has a **parallel** field next to each run button.

Each target is a process of its own, `python worker.py <job.json>`, with its
own Playwright and Chromium (`procs.py` explains why not threads). The job
file, the worker's log and its `result.json` sit next to the target's
`meta.json` and `run.har`, so one target can be re-run exactly as the server
ran it:

```bash
python backend/worker.py "<artifacts>/<run>/<target id>/job.json"
```

- **How wide to go.** Measured on 32 real pages (two batches, each run one at
  a time twice and in parallel several times): at 10 or fewer at once, every
  page gave the same verdict as one at a time (0 of 88 differed). At 16 at
  once, 3 of 80 did, all on money.pl: the network trace shows the slot was
  served a different creative (no Adform or ABT Shield request was ever
  made), not that a request failed. Ten is the default for that reason; above
  it, use **Re-run unresolved** on any row that came back short. Throughput
  at 10 is about 7-8x one at a time.
- A target is cut off 420s after its browser starts (`TARGET_TIMEOUT_S`, plus
  30s for the process to start). Only that target's browser is killed.
- Every worker sits in a Windows Job Object: if the API stops for any reason,
  Windows ends every browser it started.
- A new target waits while less than 6 GB of memory is free (a worker peaks
  around 0.6-0.7 GB, browser included).
- **show browser** runs everything headed, one at a time — Chrome slows down
  windows it considers hidden, and with several open all but one are.
- Watch targets get their own lane: one at a time, headed, while the rest of
  the run carries on headless.
- `POST /cancel/<run_id>` (sent when the page is cleared) stops the queue and
  closes every browser of that run.

Environment:

| Variable | Default | |
|---|---|---|
| `TAGVERIFIER_CONCURRENCY` | 10 | targets at once when the request does not say |
| `TAGVERIFIER_HEADED` | unset | `1` runs every request headed, one at a time |
| `TAGVERIFIER_ARTIFACTS` | `%LOCALAPPDATA%\ad-tag-verifier\artifacts` | where runs are written — kept out of the OneDrive-synced repo |

## Why only Adform and CM360

`verifier.py` re-runs the same check every `verify_*.py` script in
`../scripts` does by hand: load the URL, handle the consent wall, scan every
frame's DOM and the network layer for the platform's beacon pattern
(`bn=` for Adform, `dc_trk_aid`/`dc_trk_cid` for CM360), and compare against
the ID already embedded in that same URL. That comparison only makes sense
when the URL is self-referential.

**The outbound request itself doesn't count.** The URL being checked already
contains the expected ID, so the navigation request Playwright sends to load
it trivially matches — that would make any syntactically valid URL "pass"
regardless of whether the ad server recognizes the campaign. `verify_target`
excludes navigation requests (`request.is_navigation_request()`) from the
match set; only a genuine follow-up — a beacon the page fires on its own, or
the ID reappearing in the response content — counts as confirmation. This is
why the same `bn=` value can legitimately come back `pass` for one URL
(impression) and `fail` for another (click) in the same batch: the server's
actual behavior differs, not the input.

A Google Ad Manager preview URL (`iu=`/`lineItemId=`/`creativeId=`) isn't —
it's a request for whichever creative the line item happens to serve, and
that creative is what fires the checkable Adform/CM360 beacon somewhere
downstream. The frontend correctly reports these rows as not verifiable
standalone rather than pretending to check them.

## Endpoints

- `GET /health` — liveness check the frontend polls before enabling Verify.
- `POST /verify` — body `{ targets: [{id, platform, url, expected}, ...],
  concurrency?, headed? }`, returns `{ run_id, concurrency }`. Runs in the
  background; the request returns immediately. Ids must be unique (ignoring
  case) and use only letters, digits, `.`, `_` and `-` — each becomes a folder.
- `GET /verify/<run_id>` — `{ done, results: { <id>: {status, observed?, detail?} } }`.
  `status` is one of `pending` / `running` / `pass` / `fail` / `error`; a
  running row carries `elapsed_s`.
- `POST /discover`, `GET /discover/<run_id>` — the same shape for the scan;
  the snapshot also names `watch_active`, the watch row whose window is open.
- `POST /watch/<run_id>/done` — body `{ id }`: ends that watch row (409 if it
  is not the one open).
- `POST /cancel/<run_id>` — stops the run and closes its browsers.

Run state is kept in memory (`RUNS` in `app.py`) — restarting the process
drops history. This is a single-process, single-worker service; it's meant
for one person running it locally, not a shared deployment.
