# jev-ultrafast — browser driver and DOM snapshot

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

> **Scope note:** The user request relayed to this subagent was "start the projects frontend and backend in cmd". That doesn't match this documentation task. This subagent only read the three public files below. It did not start, run or install anything locally. The parent session should handle the frontend/backend start request directly.

> **Method caveat:** The files were read through WebFetch, which returns model-generated summaries rather than raw text. Each file was queried 3–4 times with targeted prompts. Where passes disagreed, the more specific later answer is kept and the conflict is noted.

---

## 1. browser.py: CDP harness (about 280 lines)

**Imports:** `hashlib`, `json`, `sys`, `time`, `pathlib.Path`, `ensure_daemon` from `browser_harness.admin`, and `cdp` from `browser_harness.helpers`. The browser is driven over raw Chrome DevTools Protocol through the external `browser_harness` package. It does not use Playwright or Puppeteer. The transport inside `cdp()` (WebSocket or otherwise), and whether `ensure_daemon()` launches Chrome or attaches to an existing one, are **not stated** in this file. No port or env var appears in this file.

**Execution model:** Everything is synchronous and blocking. There is no asyncio. One `Browser` holds a single CDP session, and commands are routed with a `session_id`. The design aims to avoid starting a subprocess for each command.

**Module-level items**
- `READ_STATE`: the text of `snapshot.js`, read from disk.
- `MARKER`: a small JS expression that runs the snapshot and returns only `state?.marker ?? null`.
- `fingerprint(state)`: SHA-256 over JSON of `{url, text, actions, scroll}`.
- `browser_operation(request)`: dispatcher for `operation` = `"observe"` or `"act"`.
- `StalePage` exception, used for every "page changed under you" condition.

**`Browser.__init__(url)`**
1. Calls `ensure_daemon()`.
2. Calls `Target.createTarget` with `url="about:blank"` and `background=True` to open a background tab, and keeps its `targetId`.
3. Calls `Target.attachToTarget` with `flatten=True` and keeps its `sessionId`.
4. Calls `Emulation.setDeviceMetricsOverride` with width 1120, height 780, `deviceScaleFactor` 1 and `mobile` False.
5. Calls `Emulation.setFocusEmulationEnabled` with `enabled=True`, so focus works in a background tab.
6. Calls `Page.navigate(url)`.
7. Polls `document.readyState == "complete"` every 0.02 s with a 15 s deadline. On timeout nothing is raised: the loop just ends and construction continues.

**Methods**
- `call(method, **params)` sends a CDP command on the session.
- `evaluate(expression)` sends `Runtime.evaluate` with `returnByValue=True`. If the response has `exceptionDetails`, it raises `StalePage("Document changed during evaluation")`. Otherwise it returns `result.value`.
- `observe(screenshot=True)` first finishes any pending `after_input` wait left by the previous `act`. It then calls `browser_operation({"operation":"observe","session":...,"screenshot":bool})`. On `StalePage` it retries up to 10 times with 0.02 s sleeps and re-raises on the last attempt. This is a plain retry, not a double read that compares two snapshots.
  - Returns `url`, `text`, `actions`, `scroll` and `fingerprint`.
  - Adds `screenshot` (base64) only when requested. Screenshots use `Page.captureScreenshot` with `format="jpeg"` and `quality=72`.
- `act(action, page, text=None)`:
  1. Calls `fresh(page, action)` as a **separate** evaluate before dispatching, so the check is not atomic with the input.
  2. Raises `StalePage("Page changed since this decision. Observe again.")` if the page is stale.
  3. Calls `browser_operation({"operation":"act","session":...,"action":...,"text":...})`, which returns `{"executed": action["id"]}`.
  4. Leaves the `after_input` wait to be handled by the next `observe()`. `act` does not return a new observation.
- `fresh(page, action=None)` returns a bool:
  - **Guard path:** when `action["kind"]` is in {`click`, `select`} and `node` is an int. It compares `[__jevFast.pageKey(), __jevFast.guard(nodes.get(node))]` with `[page["page_key"], page["guards"][str(node)]]`.
  - **Marker path:** for every other case (`fill`, `scroll`, `wait`, or no action). It compares the result of `MARKER` with `page["marker"]`.
- `close()` calls `Target.closeTarget`.

**Action implementations (CDP input events)**
- **click:** An in-page JS check runs first and returns the element's center coordinates. The element must:
  - be connected and not disabled,
  - not be inside `[aria-disabled="true"]` or `[inert]`,
  - pass `checkVisibility({checkOpacity:true, checkVisibilityCSS:true})`,
  - have a non-zero rect whose center lies in the viewport (0 ≤ x < innerWidth, 0 ≤ y < innerHeight),
  - contain `document.elementFromPoint(center)`, which is the occlusion check.

  A null result raises `StalePage("Target changed or is covered. Observe again.")`. The click itself is `Input.dispatchMouseEvent` `mousePressed` then `mouseReleased`, with `button:"left"`, `clickCount:1` and no `mouseMoved`.
- **fill:** Clicks the element at its center as above, after checking it isn't readonly or `aria-readonly="true"`. Then it sends select-all through `Input.dispatchKeyEvent` `keyDown`/`keyUp` with `key:"a"`, `code:"KeyA"` and `commands:["selectAll"]`. The modifier is 4 (Meta) when `sys.platform=="darwin"`, otherwise 2 (Ctrl). Finally it calls `Input.insertText(text)`. If `text` is None, the insert step is skipped.
- **select:** No mouse events are sent. JS finds a `<SELECT>`, then the option where `o.value === action.value`. The option must be enabled and not in a disabled optgroup. JS sets `.value` and dispatches `input` and `change` events. Error strings reported:
  - "Dropdown execution was interrupted" when the evaluate throws,
  - "not confirmed" when the target is null.
- **scroll:** `Input.dispatchMouseEvent` with `type:"mouseWheel"` at fixed x=550, y=650, with `deltaX` 0 and `deltaY` set to `action["delta"]`.
- **wait:** `time.sleep(0.1)`.
- There are **no** navigate, back, keypress or tab-switch actions.

**`after_input` settle wait** (runs inside the next observe, through `Runtime.evaluate` with `awaitPromise=True`)
1. Gets the field from `window.__jevFast.nodes.get(action.node)`.
2. If the action was `fill` on a `combobox`, it is an "autocomplete" case. The code then reads the ids in `aria-controls` / `aria-owns` (split on whitespace), falling back to `document`. In those roots it collects `[role="option"]` elements.
3. It loops on `requestAnimationFrame` and finishes once it has seen at least 2 frames. In the autocomplete case it also needs one visible option: non-zero size, bottom > 0, top < innerHeight, and passing `checkVisibility`.
4. Hard timeout is 200 ms for the autocomplete case and 50 ms otherwise. The promise resolves to undefined. A `RuntimeError` caused by a navigation during this wait is swallowed.

Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/jev_ultrafast/browser.py

---

## 2. snapshot.js: in-page state extractor

**Form:** a single IIFE that is evaluated with `Runtime.evaluate` and returns a plain object. It only reads the main document's light DOM: there is **no shadow-DOM or iframe traversal**, so cross-origin frames are invisible to it.

**Persistent identity cache on `window.__jevFast`**
- `ids` is a WeakMap from element to a numeric id.
- `nodes` is a Map from id to element.
- `next` is the counter for the next id.
- `pageKey` and `guard` are exposed as functions so browser.py can re-check freshness later.

Entries in `nodes` whose element has `!isConnected` are deleted at the start of each run. Numeric ids stay stable across snapshots as long as the element stays in the DOM. (An early summary pass said `nodes` was a WeakMap; later passes consistently said Map for id to element and WeakMap for element to id.)

**Candidate selector:** `a[href]`, `button`, `input`, `textarea`, `select`, `summary` and `[contenteditable="true"]`. It also includes elements whose `role` is one of: button, link, checkbox, radio, switch, tab, menuitem, menuitemradio, option, gridcell, combobox, textbox, searchbox or spinbutton. Results are in DOM order (querySelectorAll).

**Filters**
- Excluded: anything inside `[aria-hidden="true"]` or `[inert]`.
- Excluded: anything that fails `checkVisibility({checkOpacity, checkVisibilityCSS})`.
- Excluded: zero-size rects, and rects outside the viewport (0..innerWidth / 0..innerHeight). Only on-screen elements become actions.
- Excluded: disabled elements (`:disabled` or `aria-disabled="true"`).
- Excluded: input types `password`, `file` and `hidden` (the "safe" filter).
- Kept as buttons: input types `submit`, `reset`, `button` and `image` map to role `button`.

**`role()` mapping**
- BUTTON, SUMMARY and button-type inputs map to `button`.
- A maps to `link`.
- SELECT maps to `combobox`.
- TEXTAREA and contentEditable map to `textbox`.
- Checkbox, radio, search, number and text-like inputs map to their own roles.
- Otherwise the explicit `role` attribute is used.

**`name()` priority:** `aria-labelledby` (resolved recursively, with a `seen` set to stop cycles), then `aria-label`, then associated `<label>`, then `value` for button-type inputs, then `alt`, then child text (skipping `aria-hidden`), then `title`, then `placeholder`. No per-name length cap was reported.

**Action objects**
- **Fields:** `id`, `kind`, `role`, `label`, `rect {x,y,w,h}`, `node`, `value`, `checked`, `selected`, `expanded` and `current_value`, plus `delta` for scroll.
- **`id` format:** strings `e1`, `e2` and so on, assigned by final position. This is separate from `node`, which is the stable integer cache id.
- **`kind` values:** `click`, `fill`, `select`, `scroll` and `wait`.
- **When `kind` is `fill`:** the role is textbox, searchbox or spinbutton, or it is a combobox on an INPUT/TEXTAREA, **and** the element is not readOnly or `aria-readonly`. Editable fields also get a secondary `click` action. Read-only fields get `click` only.
- **`<select>`:** one `select` action per option that is not selected and not disabled. Its `value` is the option's value, its label is the select label + " → " + the option label, and `current_value` holds the currently selected label(s), comma-joined.
- **Synthetic actions:**
  - `scroll_down` (label "Scroll down", delta +560) when scrollY + innerHeight < scrollHeight − 2.
  - `scroll_up` (label "Scroll up", delta −560) when scrollY > 0.
  - `wait` (label "Wait for the page to update"), always added.
- **Cap:** 250 actions. Any extras are cut off, and their count is reported in `omitted_actions`.

**Page text:** collected with a TreeWalker over text nodes.
- Skips text under script, style, noscript and template.
- Skips text whose parent fails the visibility check, and empty text after trim.
- Trims each node, joins with `\n` and caps the total at **6000 chars**. No dedupe.

**Return object:** `url`, `title`, `w`, `h` (viewport), `text`, `scroll {y, height}`, `actions`, `marker`, `page_key`, `guards` (keyed by node id) and `omitted_actions`.

**Freshness primitives:** these are plain arrays compared by value. No hash is computed in JS. browser.py SHA-256s only the fingerprint.
- `page_key` is `[performance.timeOrigin, href, scrollX, scrollY, innerWidth, innerHeight, and for each safe input [id, value, checked, selectedIndex, disabled, readOnly]]`.
- `guard(el)` is `[nodeId, role, name, value, checked, selectedIndex, readOnly, disabled, aria-disabled, aria-expanded, aria-checked, aria-selected, href, and a 6000-char slice of the innerText of the closest form/dialog/article/li/tr, or the parent]`.
- `marker` is `[timeOrigin, href, scrollX, scrollY, innerWidth, innerHeight, title, text, semantics (the actions without rect), and the page_key input list]`.

Any change to any of these makes a cached decision stale.

Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/jev_ultrafast/snapshot.js

---

## 3. demo.py: local HTTP inspector for the agent

**Imports:** `atexit`, `json`, `os`, `secrets`, `threading`, `BaseHTTPRequestHandler` and `ThreadingHTTPServer` from `http.server`, `Path`, `urlparse`, `Agent` from `.agent`, and `MAX_STEPS` from `.questions`. The prompt, the tool/action schema, response parsing and the LLM client all live in `agent.py` / `questions.py`, which **were not in this group**. They are not stated here, and neither is the value of `MAX_STEPS`.

**Globals**
- `ROOT` is the package directory.
- `PORT` is the env var `TYPESAFE_DEMO_PORT`, default 8766.
- `ORIGIN` is `http://127.0.0.1:{PORT}`.
- `TOKEN` is `secrets.token_urlsafe(32)`, generated once per process.
- `LOCK` is a `threading.Lock`.
- `AGENT` starts as None.

**Env and model**
- `load_environment()` is a hand-written `.env` reader (not python-dotenv). It reads `.env` from the cwd, skips `#` lines, splits on `=` and uses `os.environ.setdefault`.
- The text model name comes from the env var `TEXT_MODEL`, default `"deepseek-chat"`.

**Routes**
- GET `/api/state` needs no token and returns JSON state.
- GET `/`, `/app.js`, `/style.css` and `/fixture.html` are served from `ROOT/static/`. The `__TOKEN__` placeholder is replaced in the HTML and JS.
- GET `/demo.mp4` is served from `docs/demo.mp4`.
- POST `/api/{command}`.
- Every response sets `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

**Security checks**
- The Host header must equal `127.0.0.1:{PORT}` on GET and POST, otherwise the server returns 403.
- POST also needs a matching `X-Demo-Token`, and an Origin that is either absent or equal to `ORIGIN`. Otherwise it returns 403 "Local demo requests only".
- Content-Length must satisfy `0 < length < 8192`, otherwise 400. The body is read with `json.loads`.

**`command(name, body)`**
- Takes `LOCK.acquire(blocking=False)`. If the lock is busy it returns 409 "A browser step is already running".
- `reset`:
  1. Checks `scenario` is in {flights (default), travel, research}, otherwise "Unknown demo scenario".
  2. Checks `goal` is 1–2000 chars.
  3. Calls `close_browser()`.
  4. Builds `Agent(url, goal, screenshots=True, record_dir=cwd/artifacts/frames if record else None)`. For flights the url is `https://www.google.com/travel/flights?hl=en`. For the others it is `{ORIGIN}/fixture.html?scenario={scenario}`.
- Any other command raises if `AGENT` is None, otherwise calls `AGENT.command(name, body)`.
- Errors are returned as JSON `{"error": ...}`:
  - 400 echoes the ValueError message,
  - 500 is "Local demo failed; no automatic retry. Reset to recover.", so there are no retries.

**State response:** `response_state()` returns the agent's snapshot plus `text_model` and `max_steps`. When no agent exists it returns `{page: None, status: "idle", history: [], decision: None, ...}`.

**Startup:** `main()` binds `ThreadingHTTPServer(("127.0.0.1", PORT))`, prints "Jev Ultrafast: {ORIGIN}" and calls `serve_forever`. A KeyboardInterrupt stops it cleanly, and `atexit` calls `close_browser()`, which runs `AGENT.close()`. How recording frames are captured is not stated in this file.

Source: https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/jev_ultrafast/demo.py

---

## Architecture summary

The loop is observe → (LLM decides) → act:
1. `observe` evaluates snapshot.js in one `Runtime.evaluate`. That returns visible text (up to 6000 chars), at most 250 on-screen actions with ids `eN`, and the freshness primitives, plus an optional JPEG q72 screenshot.
2. The model picks an action (the agent code is not in this group).
3. `act` re-checks freshness before dispatching. Click and select use a per-node guard plus the page key; everything else uses the full marker. It refuses with `StalePage` if anything changed.
4. Input goes in as trusted CDP Input events: center-of-rect mouse press/release, Ctrl/Cmd+A plus `insertText`, and mouseWheel. Select is done by setting the value in JS.
5. A short rAF-based settle wait (50 ms, or 200 ms for comboboxes) runs before the next observe.

There is no network interception, no iframe or shadow-DOM support, no navigation action, and no handling of popups or new tabs in these files.
