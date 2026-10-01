# jev-ultrafast — examples, tests, scripts

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

## Scope mismatch (please read)
The harness passed along this user request: "start the projects frontend and backend in cmd". The workflow script's task was something else: read the jev-ultrafast docs and source. The two don't match. I did only the read-only research task. I did not start any local servers, because the computed task says not to run anything locally and doesn't say which project is meant. The orchestrator should check whether this subagent run was what the user wanted.

Caveat on method: every page was read with WebFetch, which runs a small summarizer model over the page. Identifiers and numbers below were cross-checked by asking targeted follow-up questions. Exact counts and file names in scripts could still have small errors and should be re-checked against the raw source before anyone relies on them.

---

## examples/run.py: minimal CLI driver
- Run it with `uv run --env-file .env python examples/run.py --url URL --goal '...'`, so credentials come from a `.env` file.
- It imports only `argparse` and `from jev_ultrafast import Agent`.
- CLI flags:
  - `--url` (required)
  - `--goal` (required, `action="append"`): repeat it to pass a list of goals that run in order.
- Usage shape: `with Agent(args.url, args.goal) as agent:` and then `for state in agent.run():`. `Agent` is a context manager, and `run()` is a generator that yields state dicts.
- Fields printed per state: `elapsed_ms`, `len(history)`, `status`, and finally `page["url"]`.
- The file names no model and no specific env vars.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/examples/run.py

## examples/flights.py: Google Flights task plus an independent verifier
- `URL = "https://www.google.com/travel/flights?hl=en"`
- `GOALS` is one string: a one-way search ZRH to London, 2026-09-20, 1 adult, economy. It tells the agent to stop once matching options are visible and not to select or book.
- `Agent(URL, GOALS)` accepts a plain string here, while run.py passes a list. So the constructor takes a string or a list.
- `verify(page)` reads `page["url"]`, `page["text"]` and `page["actions"]`. It returns `{passed, checks, visible_flights}`. The checks are:
  - `search_page`: hostname `www.google.com` and path `/travel/flights/search`
  - `one_way`: the action labelled "Change ticket type. One way" has value "One way"
  - `origin`: "Where from?" has value "Zürich"
  - `destination`: "Where to?" has value "London"
  - `date`: "Departure" has value "Sun, Sep 20"
  - `year`: 2026-09-20 is found in the URL's `tfs` param, or "departing 2026-09-20" is in the page text. To read `tfs`, it pads with `=` to a multiple of 4, runs `base64.urlsafe_b64decode`, and searches for the bytes `b"2026-09-20"`.
  - `results`: flight options exist and every one contains "Sunday, September 20"
- So the verifier depends on the agent's observed `actions` list, which carries `label` and `value` per control.
- `main()`:
  - flags `--output` (default `artifacts/flights/latest`) and `--keep-open`
  - iterates `agent.run()` and prints `elapsed_ms`, `status`, `history[-1]["action"]`
  - calls `agent.snapshot()` for the final state and adds `verification` to it
  - writes `state.json`, plus `session.json` = `{target: agent.browser.target, session: agent.browser.session}`, so a later run can reattach to the same CDP target and session
  - calls `agent.close()` unless `--keep-open` is set
  - raises SystemExit (non-zero exit) if verification fails
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/examples/flights.py

## tests/test_agent.py: unit tests (pytest, Mock and monkeypatch, no real browser or model)
The tests directory lists only this one file.

Imports: `from jev_ultrafast import agent as loop`, `from jev_ultrafast import model`, `from jev_ultrafast.browser import StalePage, browser_operation, fingerprint`, `from examples.flights import verify`.

### How the model is called (TypeSafe)
- A choice has the shape `{"choice": <key>, "confidence": float, "probabilities": {key: float}}`.
- `model.validate_choice()` raises `ValueError` ("Invalid TypeSafe") on any of these:
  - a choice key that isn't in the options
  - NaN in the probabilities
  - a missing probability key
  - a negative probability
  - a choice that isn't the arg-max
  - a confidence outside the valid range (the test uses 5)
- `model.action_space(page)` returns `(elements, targets, controls)`:
  - `elements` holds one index per DOM node, listing the operations that node allows (e.g. `TYPE_TEXT`, `CLICK`)
  - `targets` is grouped by operation as `{operation: {"1": action, "2": action}}`, with string indices starting at "1"
  - `controls` includes `WAIT`
- `model.choose(page, goal, history)` makes exactly one HTTP request through `model.post_json(url, key, body)`. The body holds a `questions` dict with several heads in that one request: `operation`, plus one target head per operation (`type_text_target`, `click_target`).
- The response looks like `{"model": ..., "answers": {head: choice}}`. Only the target head that matches the chosen operation is used.
- Type safety: if CLICK is chosen but the only targets are text fields, the call fails with "Invalid TypeSafe". An out-of-range target such as "999" is also rejected.
- The target question includes control state (`checked`, `selected`) and the full rules for the next step.
- Env var: `TYPESAFE_API_KEY`.

### Text helper (a separate LLM that writes what gets typed)
- `model.field_text(...)` uses `TEXT_MODEL_API_KEY`. If the key is missing, it raises `ValueError` before typing anything.
- The request is OpenAI chat-style: `messages`, where `messages[1].content` is JSON that includes `goal`.
- The expected response is `choices[0].message.content` holding a strict JSON object `{"text": "<string>"}`. Prose ("Thinking: ..."), a null, a number or extra keys all raise `ValueError` with "nothing typed".
- Even text that appears in quotes in the task (e.g. "Zurich") still goes through the LLM, not a regex shortcut.
- There is also a `model.field_context()` helper.

### Agent loop (`loop.Agent`)
- State dict keys:
  - `browser`, `page`, `decision`, `goal`, `history`, `decisions`
  - `status` (seen: `predicted`, `ready`, `done`)
  - `started_at` (`time.perf_counter()`), `record`, `text_calls`, `screenshots`, `pending_text`
- It is driven by `command("act", ...)` and `command("tick")`.
- A stale decision is dropped before anything changes on the page: if `browser.fresh()` is False, it raises `StalePage` and `browser.act` is never called.
- Generated text is cached in `pending_text`. It is reused on a retry only when the page fingerprint is identical; if the field context changed, the text is generated again.
- Five WAIT actions in a row don't trigger a no-progress stop (status stays `ready`).
- If the action ran but the next observation raises StalePage, the action is still recorded in history.
- If the page navigates during prediction (`StalePage("Document navigating")`), `tick` re-observes the page: status goes to `ready`, `decision` is cleared, and no action runs.

### Browser layer
- Driven over raw CDP: there is a `browser.cdp(...)` function, and observation is a single atomic `Runtime.evaluate` call returning `{"result": {"value": page}}`.
- `browser_operation({"operation": "observe" | "act", "session", "action", "screenshot"})` is the in-page operation dispatcher.
- `Browser.act(action, page, text)` checks freshness before any input is sent.
- If a select ("dropdown") mutation is interrupted, it raises `RuntimeError("Dropdown execution ...")`, not StalePage, so it can't be retried as if it were stale. This covers both a response with `exceptionDetails` and an empty `result`.
- `fingerprint(page)` covers action identity (node ids) and values but ignores screenshots.
- Not stated: whether Playwright is used. The tests only show raw CDP.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/tests/test_agent.py

## scripts/ (6 files: check_guards.py, measure_flights.py, record_flights.py, render_demo.py, render_fixture.py, smoke.py)

### check_guards.py: real browser, no model calls
- Creates `Browser("data:text/html," + quote(HTML))` and calls `browser.close()` in a `finally` block.
- Uses `browser.evaluate(js)`, `browser.observe()`, `browser.fresh(page[, action])` and `browser.act(action, page[, text])`.
- What `fresh(page)` should accept (stay True):
  - a CSS transform that moves the target (the click then lands at the target's current position)
  - offscreen text changes (`#outside` at top:3000px)
  - an overlay covering the target, which leaves semantic state unchanged
- What `fresh(page)` should reject (go False): changes to
  - visible text (e.g. "Cart total")
  - an `aria-label`
  - an input value, a checkbox state, `disabled` or `readonly`
  - `display:none`
  - a replaced node (outerHTML)
  - the text of a dropdown option
- An overlay over the target blocks `act` before any input is sent (raises RuntimeError or StalePage).
- `fresh(page, action)` is a per-action guard: it accepts unrelated visible updates that the full-page guard rejects, but it rejects changes to the price text, form values, a checkbox, or the target node.
- What gets exposed as actions:
  - password fields and disabled buttons are excluded entirely
  - checkboxes, radios and readonly inputs expose only the `click` kind
  - selects use kind `select`, and the option value comes from the observed action
- Typing into a combobox waits for suggestions that appear asynchronously (60 ms setTimeout in the fixture).
- Navigating to about:blank makes `fresh` return False.
- Final line: `PASS: {len(passed)} browser guard checks; no model calls`. The summarizer counted about 23 checks; not independently verified.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/scripts/check_guards.py

### measure_flights.py: one timed live run
- Flags: `--source` (default `.`) and `--output` (required).
- Timing:
  - monkeypatches `jev_ultrafast.browser.cdp` with a `timed()` wrapper (`time.perf_counter`) that adds up the call count and total ms per CDP method
  - setup calls are excluded by `calls.clear()` before the run
  - the final `observe(screenshot=True)` happens outside the timed window
  - it reports totals per method only, with no percentiles
- Writes `state.json` with these keys:
  - `elapsed_ms`, `status`, `history`, `verification`, `error`
  - `cdp` (count and ms per method)
  - `source_hashes` (SHA-256 of every `.py` and `.js` file in `jev_ultrafast/`)
  - `task_hash`, `configuration`
  - `browser_version` (from `Browser.getVersion` product)
  - `final_page`
- Env vars recorded in `configuration`: `TYPESAFE_MODEL`, `TEXT_MODEL`, `TEXT_MODEL_BASE_URL`, `TEXT_MODEL_REASONING`.
- No model names, prices or token counts appear in the file. No explicit failure exit code.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/scripts/measure_flights.py

### record_flights.py: live run with a CDP screencast
- Imports `browser_harness.helpers.drain_events`, so it depends on a `browser_harness` package. Not stated whether that is internal or published.
- Takes one positional output dir (default `artifacts/flights/recorded`) and refuses to reuse an existing one (`exist_ok=False`).
- Recording steps:
  - takes a first screenshot with `Page.captureScreenshot`, saved as `frames/000000.jpg`
  - starts the screencast with `Page.startScreencast` (jpeg, quality 80, 1120x780, everyNthFrame=2)
  - a background thread polls `drain_events()` about every 15 ms, keeps `Page.screencastFrame` events for the agent's session, and acks each one with `Page.screencastFrameAck` and its sessionId
  - each frame is saved under `screencast/` and named by its ms offset from an epoch set just before the run starts
  - keeps recording for an extra 80 ms after the run ends to catch the final frame
- Any exception in the capture thread is added to `recording_errors`.
- Writes `state.json` (with verification and source hashes) and `session.json`.
- If verification fails it raises `SystemExit("Final-page verification failed")`. It does not call `agent.close()`. No env vars are read.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/scripts/record_flights.py

### render_demo.py and render_fixture.py: offline video rendering with Pillow and ffmpeg
**render_demo.py**
- Takes one required `source` dir and asserts `verification.passed` is true and `recording_errors` is empty before rendering.
- Renders 30 fps PNG frames on a 1536x1000 canvas.
- Overlay contents:
  - the header "browser use × TypeSafe" and a "REAL WEB · 1× SPEED" badge
  - an elapsed-time timer
  - five steps: One way / Zürich / London / 20 September / Search flights
  - a "median decision latency" figure, computed as `statistics.median` of `decisions[].latency_ms`
  - the model label, from `text_calls[0].model.split('/')[-1]`
- Outputs: `docs/demo.mp4` (libx264 crf 18, yuv420p, faststart), `docs/demo.gif` (12 fps, 1152 px wide, palettegen) and `docs/flights-result.png`.
- Uses hard-coded macOS font paths.
- State fields it reads: `history[].executed_ms` and `history[].action`, `decisions[].latency_ms` and `decisions[].elapsed_ms`, `text_calls[].model`.

**render_fixture.py**
- Reads `artifacts/final/travel-1.json` and the frames in `artifacts/final/frames/`.
- Adds a 750 ms lead-in and a 1250 ms hold at the end, on a 1240x960 canvas.
- Outputs `docs/fixture-demo.gif` (930x720) and `docs/fixture-demo.mp4`.
Sources: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/scripts/render_demo.py ; https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/scripts/render_fixture.py

### smoke.py: live model against a local fixture
- Calls `from jev_ultrafast.demo import load_environment` with no args.
- Runs `Agent("http://127.0.0.1:8766/fixture.html?scenario=travel", goal)`. It assumes the fixture server is already running and does not start it.
- Default goal: in a fake travel site, filter Lisbon "Design" stays with Free cancellation, then open "Casa Flora".
- Flags: `--max-actions` (default 15) and `--goal`. It raises RuntimeError when `len(history) >= max_actions`.
- Writes to `artifacts/dynamic/fixture/<timestamp>/`:
  - `state.json`, written while running and again at the end, including `verification_text` read with `document.body.innerText`
  - `summary.json` with keys `ms`, `verified`, `decisions`, `actions`
- Asserts that `status == "done"`, the URL ends with `#casa-flora`, and the page text contains the filter-summary string.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/scripts/smoke.py

## Not stated anywhere in this group
- Real model ids and prices.
- The TypeSafe endpoint URL.
- Measured latency numbers. They appear only at runtime, e.g. `latency_ms` in the rendered overlays.
- Rate limits and retry/backoff policy.
- How Chrome is launched or connected to, beyond the CDP target and session ids.
- Iframe and cross-origin handling.
