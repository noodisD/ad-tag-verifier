# jev-ultrafast — the core loop (`agent.py`, `model.py`, `questions.py`)

> **Research notes, 2026-10-01.** Written in our own words. Unlike the other
> files in this folder, these three source files were read through a
> *summarising* fetch rather than line by line, so treat exact numbers (retry
> counts, tolerances, limits) as "reported" and check them in the source before
> building on them. The code is MIT licensed; the TypeSafe documentation is not.

Sources:
- <https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/jev_ultrafast/model.py>
- <https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/jev_ultrafast/questions.py>
- <https://raw.githubusercontent.com/browser-use/jev-ultrafast/main/jev_ultrafast/agent.py>

## The idea in one paragraph

Each step of a browser task is **one request** to Jev carrying two multiple-choice
questions at once: *which operation next?* and *which element is the target?*
Both are Choice questions over small, numbered option sets, so no text has to be
generated and parsed. The page is described to the model as a list of indexed,
visible controls rather than a screenshot. A second, ordinary LLM is called only
when a field has to be filled with text.

## `model.py` — talking to Jev

| Piece | What it does |
|---|---|
| `post_json(url, key, body)` | Sends the request with a bearer token. Reported: three attempts on 429, 529 and 503 with a short backoff (about 0.5 s then 1 s). Connection failures and other HTTP errors raise. |
| HTTP client | One shared client with HTTP/2 and a 25 s timeout. |
| `choose(state, goal, history)` | Builds the request, calls Jev, validates both answers and returns the operation, the target, confidences, probabilities and latency. |
| `action_space(actions)` | Turns the raw list of actions into numbered elements, a map of targets per operation (click, type, select) and a map of controls. Deduplicates by node. For select controls, options get sub-indices written `index:option`. |
| `validate_choice(answer, ids)` | Refuses an answer unless: the chosen id is one that was offered; the probabilities cover exactly the offered ids; every number is finite and within 0–1; the probabilities sum to 1 within about 0.02; and the chosen id has the highest probability. |
| `field_context` / `field_text` | Build the context for a text field (goal, field label and current value, page title and text capped at roughly 6,000 characters, last few actions) and ask the secondary LLM for the text. The reply must be a JSON object with one `text` key, a non-empty string of at most about 2,000 characters. |

Configuration is by environment variable: the Jev key and model name
(`jev-latest` by default), and for the text model a base URL, model name, key and a
reasoning switch. The text model defaults to an OpenAI-compatible endpoint and is
swappable.

**State sent to Jev:** the page (URL, title, text), the elements (index, label,
supported operations, role, current value, checked / selected / expanded flags and
select options) and the last ten actions with whether the page changed.

**The two heads:**
- *operation head* — a Choice whose options are the operation names (such as
  click, done, blocked) plus any controls, each with an instruction-style label;
- *target head* — one Choice per operation, whose options are the element indices
  (or `index:option` for selects), each described by label, current value and state
  flags. Only the target head for the chosen operation is read.

## `questions.py` — the wording

Three instructions are defined: what the next operation should be, which element is
the target, and the exact text for a field. The next-action and target wording is
reported as prescriptive and rule-heavy; the text-value wording forbids inventing or
guessing. The step budget lives here: a task is capped at 60 operations. (The
operation set is described abstractly rather than listed in this file: click, type,
pick an autocomplete suggestion, choose a date, toggle, submit, wait.)

*Reported, unverified:* that the wording leans on negations ("never", "do not").
TypeSafe's own guidance (see `../typesafe-jev/05-models-api-agent-skill-legal.md`)
warns that Jev handles negation poorly, so if this is true it is worth reading the
file directly before copying the style.

## `agent.py` — the loop

1. **Predict** — call `choose()` with the current state and goal.
2. **Act** — execute the chosen operation; a `fill` first asks the text model for
   the value, which is cached so a retry does not generate it twice.
3. **Observe** — take a new snapshot and screenshot.
4. **Verify** — did the page change; update the history.

Safety rules that matter if the pattern is borrowed:
- **Freshness guards.** Before predicting, before acting and before declaring the
  task done, the page fingerprint is compared; a stale page triggers a fresh
  observation or a `StalePage` error rather than acting on old indices.
- **Mutations are never retried.** The action is consumed before it runs, so a
  retry cannot click twice. Only the *decision* may be reconsidered.
- **Stop conditions.** The task ends as done or blocked. It is blocked after three
  consecutive non-mutating actions that leave the page unchanged, and when either
  the model-call budget (twice the step cap) or the action budget is exhausted.
- **"Done" is not proof.** The terminal choice is only accepted after a freshness
  check.

`run()` yields a snapshot of the observable state after each step — goal, page,
decisions, history, elapsed time and the action-space elements — and nothing from
the browser internals.

## What this means for Ad Tag Verifier

The loop assumes a single main document it can enumerate from outside. It cannot see
into the cross-origin iframes where creatives live, and it clicks within the page
rather than following a click into a new tab (see
`02-browser-snapshot-and-driver.md`). What transfers is the **discipline**, not the
code: act only on an observed target, check it is still there and on top just before
the click, never repeat a mutation, and treat "clicked" as unproven until the
evidence agrees. See `../jev-integration-proposal.md`.
