# TypeSafe Jev — confidence and usage patterns

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

# TypeSafe docs: confidence and patterns (group docs-confidence-patterns)

Every page loaded. The pages were read through WebFetch, which passes them through a summarising model, so the example wording below is close but may not match the source exactly. Identifiers and numbers were checked across several fetches.

## 1. Confidence (`/confidence`)

**What confidence is**
- TypeSafe reports certainty as a `confidence` value from 0 to 1.
- It is derived from the shape of the probability distribution over outcomes:
  - Mass concentrated on one outcome gives high confidence.
  - Mass spread out gives low confidence.

**Which answer types carry it**
- **Choice** and **Score** answers expose `probabilities` (the distribution over the options or score levels) and `confidence`.
- For Score, the distribution is taken over your criteria levels.
- **Noul** answers have no `confidence`. The page names no replacement field. The pattern pages show Noul returning a `.noul` value between 0 and 1 (see section 3).

**Formula**
- The interactive demo (`ConfidenceExplorer`) uses `(count * peak - 1) / (count - 1)`, where `peak = max(probabilities)`.
- For three options this is `(3*max - 1)/2`.
- The page says "this demo uses" that formula. It does **not** say the production API uses the same formula for n options. The exact production measure is **not stated**.
- Because the full `probabilities` array is returned, callers can compute their own certainty measure.
- The demo has three sliders (A, B, C) that always sum to 100% and three presets:
  - Clear winner (90/6/4). By my calculation this gives about 0.85.
  - Spread out (40/33/27). By my calculation, about 0.10.
  - Even split (33.3 each). By my calculation, 0.

**How probabilities are produced**
- Whether they come from logprobs, sampling or something else is not stated.
- Calibration guarantees are not stated.

**Suggested confidence bands**

| Band | Range | Guidance |
|---|---|---|
| High | above 0.9 | Act automatically |
| Medium | 0.5 to 0.9 | Proceed with caution: confirm with the user, flag for review, or gather more information |
| Low | below 0.5 | Do not act: route to a human, ask for clarification, or use another system |

**Per-action thresholds**
- Scale the threshold to the risk of the action. Read-only actions can accept lower confidence than destructive or financial ones, such as transfers.
- Start conservative, validate on real data, then adjust.

**Code example on the page (Python)**
- Call: `client.system_one(state=user_message, questions={"action": Choice(instructions=..., criteria={...})})`.
- Option keys: `check_balance`, `approve_transfer`, `support`.
- Routing:
  - `action.confidence < 0.5` sends the request to a human.
  - `check_balance` runs directly because it is low stakes.
  - `approve_transfer` runs when confidence is above 0.9 and is verified first otherwise.
- The answer is read as `response.answers["action"]`, with fields `.choice` and `.confidence`.
- Imports and client construction are not shown.

The page links to `/primitives/choice`, `/primitives/score` and the index at `https://docs.typesafe.ai/llms.txt`.

Source: https://docs.typesafe.ai/confidence.md

## 2. Patterns index (`/patterns`)

- The page frames TypeSafe as one component inside a larger system that makes AI-driven decisions.
- It assumes you have read the primitives and confidence pages first.
- Four patterns are listed:

| Pattern | Page | Listed benefits |
|---|---|---|
| Speculative Fan-Out | `/patterns/fan-out` | Cost, Speed |
| Confidence-Gated Routing | `/patterns/confidence-routing` | Reliability, Safety |
| Composite Scoring | `/patterns/composite-scoring` | Cost, Reliability, Speed |
| Intent Routing | `/patterns/intent-routing` | Cost, Speed |

- The full index is at https://docs.typesafe.ai/llms.txt.

Source: https://docs.typesafe.ai/patterns.md

## 3. Speculative fan-out (`/patterns/fan-out`)

**Idea**
- Send many questions in one call, including ones that may turn out to be irrelevant. Your own code then ignores the answers it does not need.
- The docs say all questions are evaluated in parallel, so extra questions usually add little latency.
- No figures are given for latency, cost, billing (per question or per call), or the maximum number of questions per call.

**Request shape (JSON)**
- Top-level `state` holds the ticket text.
- Top-level `questions` maps each question key to a definition.
- Definition fields:
  - `type`: one of `choice`, `score`, `noul`.
  - `instructions`: a string.
  - `criteria`:
    - For choice: an object mapping option keys to descriptions.
    - For score: an ordered array of level descriptions, where index = score value.
    - For noul: omitted.

**Example: support-ticket triage, five questions**

`category` (choice). Instructions: find the broad category of the ticket. Options:
- `bug_report`: something is broken or producing errors
- `billing`: charges, invoices, refunds, subscriptions
- `feature_request`: new functionality
- `account`: login, permissions, profile, security

`bug_severity` (score, 3 levels):
- 0: cosmetic, no functional impact
- 1: broken or degraded, with a workaround
- 2: blocking, with no workaround

`has_reproducible_steps` (noul). Instruction: the user describes specific steps to reproduce.

`refund_requested` (noul). Instruction: the user explicitly asks for a refund or credit.

`frustration` (score, 3 levels):
- 0: calm
- 1: frustrated but civil
- 2: very angry

**Routing logic (Python)**
- If `category.choice == "bug_report"`:
  - If `bug_severity.score > 1.5` and `has_reproducible_steps.noul > 0.6`, call `escalate_to_engineering(ticket_id, severity="high")`.
  - Otherwise call `add_to_bug_backlog(ticket_id)`.
- If `billing`:
  - If `refund_requested.noul > 0.7`, call `route_to_billing_with_flag(ticket_id, refund_likely=True)`.
  - Otherwise call `route_to_billing(ticket_id)`.
- If `feature_request`, call `log_feature_request(ticket_id)`.
- After that chain, a separate `if frustration.score > 1.5` calls `flag_for_priority_response(ticket_id)`. This applies to every category.

**Things to note**
- `.score` is compared to 1.5 on a 0–2 scale. That suggests `.score` is a continuous value, probably an expected value over the levels, rather than an integer. The docs do not state this.
- `.noul` is treated as a probability from 0 to 1.
- The page has a "Try it in the Playground" link to `https://console.typesafe.ai/decode#share/...`.

Source: https://docs.typesafe.ai/patterns/fan-out.md

## 4. Confidence-gated routing (`/patterns/confidence-routing`)

**Idea**
- The answer says what to do; confidence says whether to act on it.
- Confidence works as a second decision axis, with thresholds chosen by how bad a wrong action would be.

**Example: voice banking**

A single choice question `intent`, with instructions asking what action the user wants. Options:
- `check_balance`: check an account balance
- `approve_transfer`: approve the pending transfer
- `other`: something else

**Routing, in order** (from `action = response.answers["intent"]`):

| Check | Action |
|---|---|
| `action.confidence < 0.6` | `route_to_support_agent(account_id)` (a floor that applies to every action) |
| `check_balance` | `show_balance(account_id)` |
| `approve_transfer` with confidence above 0.85 | `approve_transfer(account_id)` |
| `approve_transfer` otherwise (0.6–0.85) | `ask_user_to_confirm("Just to confirm: ...")` |
| Anything else | `route_to_support_agent(account_id)` |

**Things to note**
- The thresholds are justified only by the consequences of a wrong classification. No calibration method or data is given.
- The page does not show how the transcript maps to `state`. It is presumably passed as `state`.
- No latency or cost figures are given.
- There is a Playground link, and the page links back to `/confidence`.

Source: https://docs.typesafe.ai/patterns/confidence-routing.md

## 5. Composite scoring (`/patterns/composite-scoring`)

**Idea**
- Split a complex judgment into small, atomic score questions asked in one request.
- Combine the scores in your own code with weights you control. You can re-weight without calling the API again.

**Example: resume screening**
- One request carries the resume as `state` and four `score` questions, each with five levels (0–4).
- `python_depth`, levels 0–4:
  - none mentioned
  - mentioned, no detail
  - used in projects
  - primary language
  - deep expertise
- `team_leadership`:
  - none
  - informal mentor or tech lead
  - led a small team
  - managed direct reports
  - managed multiple teams or an org
- `system_design`:
  - none
  - contributed to design discussions
  - designed components
  - owned a significant system's architecture
  - designed at scale across multiple domains
- `generalist`:
  - one domain only
  - narrow variety
  - a few areas or stacks
  - regularly moved between domains
  - a track record of ramping up in unfamiliar areas

**Scoring code**
- Each score is normalised as `response.answers[k].score / 4`, giving 0–1.
- IC weighted total: `0.40*py + 0.10*lead + 0.40*arch + 0.10*general`.
- EM weighted total: `0.15*py + 0.40*lead + 0.20*arch + 0.25*general`.
- The diagram flow is: resume, then 4 parallel questions, then normalise, then weight, then rank. No sort code is shown.

**Things to note**
- The example does not use `.confidence` or `.probabilities`.
- Whether `.score` is an integer or a float is not stated (the fan-out thresholds suggest a float).
- No latency or cost figures are given. There is a Playground link.

Source: https://docs.typesafe.ai/patterns/composite-scoring.md

## 6. Intent routing (`/patterns/intent-routing`)

**Idea**
- Put TypeSafe in front of your handlers as a fast, cheap classifier.
- Send each request to deterministic code, a specialist LLM, or a human, so expensive resources are used only where they are needed.
- No latency, price or model-name figures are given.

**Example: customer service, two parallel questions in one request**

`intent` (choice). Instructions: the primary intent of the customer message. Options:
- `order_status`: an existing order
- `product_question`: a question before buying
- `return_exchange`: a return or exchange
- `complaint`: unhappy and wants resolution

`complexity` (score, 3 levels):
- 0: simple lookup or standard procedure
- 1: needs judgment or several steps
- 2: unusual, an edge case, or needs escalation

**Routing: `route_ticket(ticket_id, response)`**
- If `intent.confidence < 0.5`, call `route_to_human_agent(ticket_id)` and stop.
- `order_status` calls `handle_order_status(ticket_id)` (deterministic lookup).
- `product_question` calls `handle_with_llm(ticket_id, PRODUCT_SPECIALIST)`.
- `return_exchange` calls `handle_with_llm(ticket_id, RETURNS_SPECIALIST)`.
- `complaint`:
  - If `complexity.score > 1` or `complexity.confidence < 0.5`, send to a human.
  - Otherwise call `handle_with_llm(ticket_id, COMPLAINT_RESOLUTION)`.
- There is no `else` fallback. The page does not say what happens for an unmatched choice.

**Playground encoding**
- A `TypesafeExample` component (props `example`, `display`, `title`) builds the Playground link.
- It creates `{apiVersion: "v1", documentText: <state>, promptsText: JSON(questions), selectedModels}`.
- That object is compressed with LZ-string `compressToEncodedURIComponent` and appended to `https://console.typesafe.ai/decode#share/`.
- No `selectedModels` value is shown.

Source: https://docs.typesafe.ai/patterns/intent-routing.md

## Across all pages
- **Endpoint and auth:** none of these pages give an HTTP path, auth header, rate limit or error codes.
- **SDK:** the only SDK method shown is `client.system_one(state=..., questions=...)`, with a `Choice(...)` class. Other pages use raw JSON dicts.
- **Answer shape:**
  - `response.answers[key]` holds the answer for each question key.
  - Choice answers have `.choice` and `.confidence`.
  - Score answers have `.score` and `.confidence`.
  - Noul answers have `.noul` (0–1).
  - Choice and Score answers also have `probabilities`.
- **Thresholds seen across pages:**
  - Confidence floors: 0.5 (confidence page, intent routing) and 0.6 (banking).
  - Auto-act for high stakes: above 0.85 (banking) or above 0.9 (confidence page).
  - Noul thresholds: 0.6 and 0.7.
  - Score thresholds: above 1.5 on a 0–2 scale, and above 1 on a 0–2 scale.
