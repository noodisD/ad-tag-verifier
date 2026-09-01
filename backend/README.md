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
- `POST /verify` — body `{ targets: [{id, platform, url, expected}, ...] }`,
  returns `{ run_id }`. Runs on a background thread; the request returns
  immediately.
- `GET /verify/<run_id>` — `{ done, results: { <id>: {status, observed?, detail?} } }`.
  `status` is one of `pending` / `running` / `pass` / `fail` / `error`.

Run state is kept in memory (`RUNS` in `app.py`) — restarting the process
drops history. This is a single-process, single-worker service; it's meant
for one person running it locally, not a shared deployment.
