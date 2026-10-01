# jev-ultrafast — README, performance report, AGENTS.md

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

## Scope mismatch (read first)
The user request relayed by the harness was "start the projects frontend and backend in cmd". That has nothing to do with this computed doc-reading task. I did only read-only public web fetches. I did not start, run or install anything locally. The orchestrator should check whether this workflow was routed to the wrong place.

Method caveat: WebFetch passes each page through a small summarizer model, so the notes below are paraphrases of what it returned, not raw text. Exact identifiers and numbers were cross-checked over several fetches where possible. Source files under `jev_ultrafast/` (agent.py, snapshot.js, browser.py, model.py, questions.py, demo.py, static/app.js) were not in this group and were not read.

---

## What it is
jev-ultrafast (v0.1.0, MIT, Python >=3.12) is a browser automation agent. It picks from a dynamic, indexed action space and does not generate selectors or code. The tagline in pyproject reads roughly "a browser agent that chooses instead of generating." It takes one natural-language goal. The headline demo is a Google Flights one-way search, Zurich to London, in about 7.1 s (7,073 ms) at 1x speed.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/README.md

## Architecture / loop
- The loop is: page -> indexed element table -> one TypeSafe request returning operation + target -> execution.
- **State:** a structured DOM snapshot, not screenshots. `snapshot.js` takes an atomic DOM snapshot of indexed controls with freshness guards, in a single browser call per snapshot. Each observation builds an element table with one row per control: index, role, accessible name and current value (for example `[2] combobox Where from? · San Francisco`). Screenshots are optional and the model never sees them.
- **Model call:** one TypeSafe request per cycle returns two decision heads, operation and target. The README lists the outputs as operation / `click_target` / `type_text_target` / `select_target` (the last only if present), with probabilities per operation and per target. The demo inspector shows these probabilities. The endpoint name and full request schema are not stated beyond the element table plus goal.
- **Operations:** `CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, `BLOCKED`. `SELECT` carries an observed element/option index for native dropdowns. SCROLL and BLOCKED semantics: not stated.
- **Text generation:** a separate small LLM runs only when the operation is `TYPE_TEXT`. Its output must parse as a small JSON object before anything is typed. The JSON schema is not stated. Model output never becomes selectors, coordinates or JavaScript.
- **Caching:** an interrupted (stale) text request is reused only while the entire helper input is unchanged.
- **Target validation:** every executed target resolves to an observed node. Before input, the executor rechecks page freshness and click occlusion and rejects covered controls. Geometry and hit-testing run before input. Click guards compare the chosen target and nearby context plus document/form state. They deliberately allow unrelated visible updates instead of invalidating on every DOM mutation.
- **Waits:** after TYPE_TEXT into a combobox, an event-based wait for visible suggestions, capped at 200 ms. Otherwise at most two animation frames or 50 ms.
- **Mutation policy (AGENTS.md):** mutations are logged before results are observed, and browser mutations are never retried.
- **DONE** is not proof of success. Outcomes need independent verification.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/README.md
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/AGENTS.md

## Browser driving
- Chrome is driven through the `browser-harness` package (pinned ==0.1.13) over Chrome remote debugging (CDP). The user allows remote debugging in Chrome when prompted.
- The agent uses "owned tabs" inside the user's existing Chrome profile, with focus emulation to prevent background-tab throttling.
- Whether Playwright is involved: not stated (browser-harness is the dependency).
- Not supported: iframes/frames, shadow roots, canvas, uploads, pop-up/new tabs, nested scrolling, arbitrary keyboard widgets. Cross-origin handling: not supported, since frames are not traversed. Network interception: not stated.
- The DOM reader handles common HTML/ARIA controls but does not implement the full accessible-name spec.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/README.md
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/docs/performance.md

## Files
- `agent.py`: the full loop and the hand-off to the text helper
- `snapshot.js`: atomic DOM snapshot and indexed controls
- `browser.py`: connection, geometry, execution
- `model.py`: dynamic operation/target heads and text generation
- `questions.py`: model instructions
- `demo.py`: local inspector (entry point `jev` = `jev_ultrafast.demo:main`)
- `static/app.js`: inspector front end
- `examples/run.py`: Wikipedia task
- `examples/flights.py`: flights task with outcome verification and trace saving
- `scripts/record_flights.py`: records with original timestamps
- `scripts/render_demo.py`: renders verified runs
- `scripts/check_guards.py`: tests guards without model calls
- `docs/`: banner.svg, demo.mp4, demo.gif, performance.md
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/README.md

## Setup / usage
- Setup: `git clone`, `uv sync` (also installs Browser Harness), `cp .env.example .env`.
- `uv run jev` starts the inspector at http://127.0.0.1:8766. It shows the numbered elements, operation/target probabilities and executed actions.
- Library: a context manager `Agent(url, goal)`. `agent.run()` is a generator yielding state dicts with at least `elapsed_ms` and `status`. Other keys and constructor parameters: not stated.
- CLI: `uv run --env-file .env python examples/run.py --url <url> --goal <text>`.
- Budgets (max steps/actions/requests) exist (the performance doc mentions shared action/request budgets), but the numbers are not stated.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/README.md

## Env / auth
`.env.example` defines:
- `TYPESAFE_API_KEY` (empty)
- `TYPESAFE_MODEL=jev-latest`
- `TEXT_MODEL_API_KEY` (empty, kept server-side)
- `TEXT_MODEL_BASE_URL=https://openrouter.ai/api/v1`
- `TEXT_MODEL=inception/mercury-2.5`
- `TEXT_MODEL_REASONING=none`

Any OpenAI-compatible endpoint works for the helper; Gemini, GLM and DeepSeek are named. `.env` is gitignored.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/.env.example

## Dependencies / tooling
- Runtime: `browser-harness==0.1.13`, `httpx[http2]>=0.28,<1`
- Dev: `pytest>=8.4,<9`, `ruff>=0.14,<1`, `pillow>=11,<13`
- Build: hatchling. Ruff: line length 120, rules E/F/I. Pytest: `tests` directory.
- Required checks (AGENTS.md): `uv run ruff check .`, `uv run pytest`, `node --check jev_ultrafast/static/app.js`, `uv build`. Tests must not call paid APIs.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/pyproject.toml
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/AGENTS.md

## Performance
- **Matched comparison:** 3 alternating pairs (6 runs), same goal, 1120x780 viewport, one Chrome profile, independent result checkers, shared budgets. All 3/3 runs verified in each arm.

| Pair | Original | Optimized |
|---|---|---|
| 1 | 11.214 s | 6.964 s |
| 2 | 8.984 s | 7.913 s |
| 3 | 9.450 s | 7.092 s |
| Median | 9.450 s | 7.092 s (-25.0%) |

- Median TypeSafe requests fell from 22 to 17. Browser protocol calls fell from 1,092 to 101.
- The authors' own caveat: three pairs are too few for a strong claim (sign test p = 0.25).
- **What changed:** the original invalidated decisions on every DOM mutation (including animations), read the accessibility tree repeatedly and resolved hundreds of nodes per cycle. The optimized arm uses one-call snapshot reads plus click guards and an event-based combobox wait.
- **The 7.073 s showcase run:** 17 Jev requests, 10 interactions plus 1 explicit WAIT, 2 helper calls. Median Jev latency 178 ms. Search fired at 5.217 s, done at 7.073 s. Helper latency: "Zurich" 581 ms, "London" 346 ms. TypeSafe tokens: 90,558 in / 6,325 out. Helper cost via OpenRouter: $0.00006272 for 2 calls. TypeSafe pricing and browser infrastructure costs are not stated.
- **Timing boundary:** starts after the initial page observation. It excludes browser setup and navigation but includes model, text, browser and loading time.
- **Versions:** TypeSafe `jev-1.13.0`, helper `inception/mercury-2.5` with reasoning off. Original frozen source commit `68c077bf79caca4e817b8e8a5854b2efa0c81ff6`. Evidence files: `flights-measurement.json`, `full-speed-measurement.json`. Chrome version, OS and network: not stated.
- **Smoke checks:** Wikipedia (Godel's incompleteness theorems article, exact URL verified) 2.798 s. A local hotel fixture site (Lisbon, filters Design and Free cancellation, opens Casa Flora) 1.896 s.
- **Helper probe:** 6 calls tested Gemini 2.5 Flash Lite, Gemini 3.1 Flash Lite and Mercury 2.5. All were correct on the tiny sample. No per-model latencies.
- **Development attempts (not part of the comparison):** original 9.302 s; accessibility-tree candidates 9.395 s and 10.157 s; first direct-DOM candidate 8.697 s but failed verification (incomplete name/value extraction); after the label/combobox fix 8.051, 8.631, 8.395, 8.385 and 7.741 s; a Mercury diagnostic 7.559 s.
Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/docs/performance.md

## Repo page
- Default branch `main`, Python, MIT. The summarizer reported 3 commits.
- Top level: `.env.example`, `.gitignore`, `AGENTS.md`, `LICENSE`, `README.md`, `pyproject.toml`, `uv.lock`, `docs/`, `examples/`, `jev_ultrafast/`, `scripts/`, `tests/`.
- The summarizer also reported 21.6k stars and 1.5k forks. That looks implausible for a 3-commit repo and may be a summarizer error or org-level numbers. Treat it as unverified.
Source: https://github.com/browser-use/jev-ultrafast
