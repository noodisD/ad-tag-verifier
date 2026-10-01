# Would Jev or jev-ultrafast make Ad Tag Verifier more efficient?

**No — not as a dependency, and not as a swap for the model calls we already make.**
Jev is a fast, text-only model for small multiple-choice decisions. This project's
time is not spent on decisions; it is spent waiting for ad servers. What *would*
pay off is smaller and does not involve Jev: run pages concurrently, and tighten
the one click path that still uses raw coordinates.

Reference notes: [README.md](README.md). Dated 2026-10-01.

## 1. Where the time goes (measured)

| Step | Measured | Model involved? |
|---|---|---|
| dziennik.pl, creative not yet served | 230–260 s per page, nearly all waiting for Google Ad Manager | no |
| dziennik.pl, creative served at once | about 47 s | no |
| A 14-page scan of one bank client's campaign, one page at a time | about 50 minutes | no |
| Interia / OLX pages | 20–130 s | no |
| Video pre-roll, tab in front | 30–45 s; the same page took 232 s with the tab hidden | no |
| Email-to-sheet pairing (`core/ai/match.py`) | once per email, seconds | yes — and **not wired into the UI today** |
| Vision click fallback (`core/ai/creative_click.py`) | a few seconds, only when no clickable frame is found | yes |

Jev answers in roughly 100–150 ms (the docs say 70–500 ms end to end; the
`jev-ultrafast` demo measured a 178 ms median). Against a 230 s wait that is
0.1 %. Price is not a lever either: $0.042 per million input tokens, output free.

## 2. What each thing is, and why it does not fit

**Jev (the model).** One request carries a text `state` plus typed questions
(Choice up to 255 options, Score, Noul) and returns the answers with
probabilities and, for Choice and Score, a confidence. Text only — the docs say no
images. English is the primary language; other languages are less accurate. It is
literal, weak on numbers, arithmetic and indirection, does not revise an answer,
and "adversarial text can move it". Early access since mid-September 2026; the SDK
had its first public release on 2026-09-14 and breaking changes in 0.6.0 and 0.7.0.

**`jev-ultrafast`.** A browser agent built on Jev (MIT, v0.1.0, a very young repository). It
describes the page as a numbered list of visible controls and asks Jev, in one
request, *which operation* and *which element*. It does not fit because:

| Needs | `jev-ultrafast` | Consequence |
|---|---|---|
| One Playwright-owned browser that records the HAR | Drives the user's own Chrome over raw CDP through `browser-harness` | The HAR — our evidence — would no longer be recorded by us |
| See into cross-origin iframes (where creatives live) | Reads only the main document's light DOM; no iframe or shadow-DOM traversal | Cannot see an ad creative or an iframe-hosted consent wall |
| Follow a click into a new tab | No pop-up or new-tab handling | Cannot capture the landing page or the click beacon's tab |
| Elements anywhere on the page | Only on-screen, indexed, capped at 250 | Misses off-screen slots |
| Speed that matters at 230 s | Its own 25 % gain is measured on a 7 s task (9.45 s to 7.09 s, three pairs) | Irrelevant at our scale |

## 3. The six proposals the review produced, and what survived

The research workflow had two architects propose and a sceptic review each.
Their verdicts, then checked against **this** repository:

| # | Proposal | Reviewer | After checking the real code |
|---|---|---|---|
| 1 | Concurrent isolated Playwright contexts, video and watch kept serial | viable with changes | **Do it.** Only change that moves a measured number. |
| 2 | Jev picks the consent button; `is_login_or_paywall` shortcut | not viable | **Reject.** Polish labels, and the shortcut lets a model skip evidence. |
| 3 | Jev decides the unresolved email-to-sheet tail | not viable | **Reject.** `/match` has no caller in the UI today (checked: zero uses in `frontend/index.html`). |
| 4 | Jev ranks structured frame/link candidates to pick our creative | viable with changes | **Mostly already built.** The frame that fired our impression is already the target (`_creative_frame`); the repo README records that targeting method as one of four that failed on slot refresh. Jev would see hosts and size buckets, which carry no advertiser identity. |
| 5 | Index-chosen, guard-checked clicks (pattern only, no dependency) | viable with changes | **Do the part that is missing**, see 4B below. |
| 6 | Jev second opinion on pairing, in shadow | viable with changes | **Reject for now**, same reason as 3. |

One caution about the review itself: the sceptics and one architect opened an older
flat folder of scripts (`run_lz.py`, `wyniki_lz.json`) instead of this repository, so
file-level remarks citing those names do not describe this code. The conclusions
about Jev's capabilities come from the documentation notes and stand; every
code-level claim above was re-checked here.

## 4. What to build

### 4A. A worker pool for display-only targets — the one real gain

Today `backend/app.py::_run_worker` opens one `sync_playwright()` and one browser and
loops through targets one at a time (`core/cli.py` does the same).

Design:
- K worker threads (start with 3), each owning its **own** `sync_playwright()` and
  `chromium.launch`, pulling targets from a `queue.Queue`. Playwright's sync API is
  bound to the thread that created it — this project hit exactly that error
  ("Cannot switch to a different thread") when `ctx.close()` was moved to a worker
  thread — so a browser cannot be shared across workers.
- Results are already keyed by target id and written under a lock
  (`_set_result`), and every target already gets its own context and HAR folder, so
  nothing else about isolation needs to change.
- **Keep video and watch serial** (`strategies.NEEDS_WINDOW`) in a separate headed
  lane. Display-only targets can run headless; a mixed run currently makes
  *everything* headed.
- Do not touch the analyzer, the stop rule (stop when one of the sheet's IDs
  fires) or any verdict logic.

Expected effect, until measured: 14 pages at 230–260 s each is about 22 minutes
with K=3 and about 17 with K=4, against about 50 now.

Risks, in order: Google Ad Manager may serve differently under parallel loads from
one IP (unknown); memory (roughly 0.3–0.5 GB per Chromium, HARs of 28–83 MB each);
and the reason runs were sequential in the first place was never written down.

**Validate before trusting it:** take 4 dziennik targets with known results, run them
once serially and once with K=4, and compare the fired IDs, the verdicts and the
time to the first sheet ID per page. Roll out only if they match.

The idea in the review of enabling focus emulation per page is dropped: Playwright
already does it for every Chromium page. The video tab problem is visibility, not
focus.

### 4B. Guard the model-click path, and say why a click was refused

The frame path already clicks the element, scrolls it into view, re-measures and
refuses an off-screen target (`_click_creative`). Two weaknesses remain:
- the **vision path** (`_clicked_at`) clicks raw coordinates the model returned,
  with no check that anything sits there or that the page has not reflowed since the
  screenshot;
- the frame path falls back to `page.mouse.click(cx, cy)` as a "last resort" when
  `el.click()` fails — a blind-coordinate click, the thing the rest of the code works
  to avoid.

Change, in plain Playwright (the principle comes from `jev-ultrafast`; none of its
code is used):
1. Resolve the model's point with one in-page `elementFromPoint`, walk up to the
   nearest slot container (iframe, `a`, `canvas`, GAM slot div or a node with an
   `onclick` or background image) and require overlap with the model's box. If
   nothing qualifies, **refuse** — do not click empty coordinates.
2. Record a guard at decision time (slot id, iframe name, rect) and re-check it just
   before the click; allow one re-resolve, otherwise refuse.
3. Click through the element, not the point. Drop the raw-coordinate last resort.
4. Never repeat a click. A click is credited only by a beacon carrying the expected
   ID — already true.
5. Log a **reason code** for every refusal (`occluded`, `moved`, `no_observed_node`,
   `off_viewport`).

Value: no change in timing. The reason codes answer a question we cannot answer
today — how many untested clicks are geometry errors rather than choosing the wrong
creative — after one dense run.

### 4C. Worth investigating, with no commitment

Reports keep saying "no tags fired" when the real situation is that the preview did
not serve our creative at all (moto.pl, and seven of fourteen dziennik placements).
Telling the two apart from the HAR — did the ad request that carried the preview
token come back with our line item's creative? — would make the report say what is
actually wrong. It needs a look at the ad responses first; no design yet.

### 4D. Housekeeping that makes runs cheaper

- Artifacts are written into a OneDrive-synced folder at 28–83 MB per page.
  Moving `core/artifacts/` outside the synced tree costs nothing.
- Most of a HAR is response bodies (22.5 of 28.1 MB in one measured run). Do **not**
  switch bodies off wholesale: the broken IAS snippet in the DV360 creative was found
  in a response body. If size matters, exclude heavy media by URL pattern
  (`.mp4`, `.webm`, `.woff2`, `.jpg`) and keep `.gif` and `.png`, because tracking
  pixels are often exactly those.

## 5. When Jev would be worth another look

Only if **all** of these hold:
1. `api.typesafe.ai` is reachable from the machines that run the tool. From the
   development machine a direct connection currently fails at the certificate
   revocation check, and the company URL filter blocks part of `docs.typesafe.ai`.
   Ask IT to allow-list, do not work around it.
2. Sending advertiser and campaign names to a third party is approved. TypeSafe
   states that requests are not used for training; zero data retention is an
   enterprise feature.
3. A use case exists that is text in, a choice out, in English, off the critical
   path — and a labelled set to test it on (for example a log of which creative was
   right on the pages that went wrong). None of the three candidate uses meets that
   today: consent handling needs Polish, pairing has no caller, and creative
   selection lacks the advertiser signal in text.

Even then it would start as a shadow script over logged data, never inside the live
run, and a Jev answer would never decide a verdict.

## 6. Priorities

| Do | Effort | What it buys |
|---|---|---|
| 4A worker pool | M | about 50 min to about 20 min on a 14-page scan |
| 4B model-click guard and reason codes | S | fewer wrong clicks; the data to know why clicks fail |
| 4D move artifacts out of OneDrive | S | faster writes, no cloud sync of campaign data |
| 4C preview-did-not-serve detection | investigate | reports that name the real cause |
| Jev | — | not now |
