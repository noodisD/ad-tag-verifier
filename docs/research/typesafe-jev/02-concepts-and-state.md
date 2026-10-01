# TypeSafe Jev — concepts, System One, state

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

# TypeSafe docs: Concepts group (System One, State, How to build, Use-case map)

All four pages loaded. WebFetch returns pages through a summarizing model, so I re-fetched each page with targeted prompts to pull out code blocks and exact field names. All notes below are paraphrased. Each page points to the full doc index at https://docs.typesafe.ai/llms.txt.

---

## 1. What System One is

- **System One** is TypeSafe's name for a model class that makes fast, structured decisions that software can use directly. **Jev** is the flagship model and the first System One model.
- **How it differs from an LLM:**
  - It does not generate text. It evaluates an input **state** against **questions** and returns **typed answers with probabilities**.
  - Models are trained for calibration: probabilities are optimized against real outcomes.
  - The page says calibration is measured **across groups of predictions**. It does not guarantee that any single answer is correct.
- **Input limits:** text only. Accepted inputs are strings, JSON objects and arrays of text. Images, audio and video are not supported ("yet").
- **The three primitives** (answer types). The page has a table of primitive, example question and example output:
  - **Choice**: picks one option from a set.
    - Example question: which team should handle this ticket, `billing` / `technical` / `account`.
    - Example output: `choice: "billing"`.
  - **Score**: a number on an ordered scale.
    - Example question: customer frustration, where 0 = calm, 1 = frustrated, 2 = very frustrated.
    - Example output: `score: 1.4`. Fractional values are possible.
  - **Noul**: a true/false property returned as a probability.
    - Example question: does this message request a refund.
    - Example output: `noul: 0.95`.
- **Example workflow (refund case):**
  1. Build a state that holds the customer message, the relevant transactions and the refund policy.
  2. Ask independent questions in the same request: was a refund requested, does the evidence show a duplicate charge, does the policy support a refund.
  3. Combine the answers with deterministic checks in code, then route the case to action or to review.
- **Access:**
  - Call it through a client SDK or over HTTP with `POST /v1/systemone`.
  - The `model` field selects the model. The docs use `jev-latest`, which is also the SDK's default.
- **Confidence:** every answer also carries a confidence value, so code can decide whether to act or escalate (to a human or a reasoning model). Details are on `/confidence`.
- **Not stated on this page:** latency figures, pricing, rate limits, auth. It links to `/models` for pricing and aliases, `/api`, `/sdk` and `/introduction/machine-learning-primer`.

Source: https://docs.typesafe.ai/concepts/system-one.md

---

## 2. State (the input)

- **What it is:** the content being evaluated, sent in the request's `state` field together with one or more questions.
  - One request evaluates one state against many questions.
  - Each question is answered independently.
  - Question types can be mixed in one request (Choice, Score and Noul together).
- **Three accepted shapes** (shown as Python values):
  - **String**, for a single message, article or passage. Example: a one-line complaint about a double charge.
  - **Object**, a dict of named fields such as `message` and `order_id`. The docs recommend this shape for most requests, because it keeps related facts clear and linked.
  - **Array**, a list of messages or records. Example: three chat turns as strings.
- **Larger example state:**
  - `ticket`: `subject`, plus `messages`, a list of `{from, text}` entries.
  - `order`: `id`, plus `charges`, a list of `{amount_usd, status}`.
  - `refund_policy`: a string.
- **Design rules:**
  - Group related information together when a decision needs parts to be compared against each other.
  - The state holds content and supporting facts. The questions hold the judgments. For example, put the refund request and the policy in state, then ask about each with separate questions.
- **Limits:**
  - Text only. No images, audio or video.
  - Trained mainly on English. Other languages, CJK scripts included, have lower accuracy.
  - Maximum state size (characters or tokens): **not stated**.

Source: https://docs.typesafe.ai/concepts/state.md

---

## 3. How to build with System One (design method and request shape)

### Core idea

- Code stays in control of the program. System One gets narrow, structured decisions.
- **Three architectures compared:**
  - **Traditional software:** complex decision trees built from reliable primitives.
  - **LLM agents:** the model reads instructions and picks the next step. Every loop is another chance to fail, so they need monitoring.
  - **AI-powered software** (the recommended one): code owns determinism and control flow. Models are called only where common sense or reading unstructured data is needed, as small atomic tasks.

### Why System One composes well (six properties)

1. **Structured:** type-safe by construction. Answers conform to a JSON schema, so nothing has to be parsed out of prose.
2. **Parallel:** questions are evaluated independently. No hidden context leaks between them.
3. **Comparable:** outputs are sortable, so thresholds and conditions work on them.
4. **Fast:** most queries finish in about **100 ms**.
   - The use-case page says **150 ms** instead. Both figures appear in the docs.
5. **Calibrated confidence:** RLCD (explained on `/introduction/machine-learning-primer`) expresses uncertainty as calibrated probabilities rather than leaning overconfident.
6. **Self-consistent:** repeated calls give stable answers (see `/cookbooks/consistency_noul_cookbook`).

Stated goal: an intelligence-to-speed-and-cost ratio better than 100×.

### Design steps (headings in page order)

1. **Use code when you can.** Deterministic logic stays in code. The example computes invoice days overdue and sends the invoice to collections when it is more than 30 days late, with no model call.
2. **Decompose the input state.**
   - Send only the context the current questions need; the page says this avoids distraction and "context rot".
   - Prefer current knowledge-base facts over whatever is in the model's weights.
   - Example: a flight-refund check sends only `ticket_message` and `refund_policy`.
3. **Use structure in the input state.**
   - Send nested JSON.
   - Inside a question's text, point at nested values with **backtick-wrapped dot/index paths**, for example `` `support.tickets[0].message` `` or `` `commerce.orders[0].charges` ``.
4. **Decompose the questions.** The page calls this probably the most important idea in the guide. Replace one broad question with many narrow atomic ones.
   - **Spam example.** Instead of "is this spam?", it asks six Noul questions:
     - `requests_credentials`, `offers_unexpected_reward`, `creates_time_pressure`
     - `sender_identity_mismatch`, `link_domain_mismatch`, `disguises_link_destination`
     - Each one references paths such as `message.body`, `message.sender.email` and `message.links[0].url`.
   - **Tool-call verification example.** Instead of "are the tool calls correct?", it asks nine Noul questions:
     - `geocode_tool_is_relevant`, `geocode_location_matches`, `geocode_arguments_match_schema`, `geocode_result_matches_call`
     - `weather_tool_is_relevant`, `weather_arguments_match_schema`, `weather_uses_geocoded_coordinates`, `weather_date_matches`, `weather_unit_matches`
     - The state holds `request`, `available_tools` (each with `description` and a `parameters` schema) and `trace` (`tool_calls` with `id`/`name`/`arguments`, and `tool_results` with `tool_call_id`/`output`).
     - In the example the planted error is the unit: `celsius` was used where `fahrenheit` was asked for.
5. **Use structure in the questions.**
   - `instructions` and `criteria` are usually strings but may be objects or arrays.
   - Use structure when a question needs context or examples, when values come from code (put the record in its own named field instead of building a string template), or when several questions share instructions.
   - **Resume dedup example:** `instructions` is an object holding `potential_duplicate` (`name`, `location`, `last_employer`) and `question`. The question text refers to it as `` `potential_duplicate` ``.
   - **Contrastive Choice example:** `instructions` holds `{question, focus}`. `criteria` maps each option key to `{what, not_for, examples[]}`.
   - Short, unambiguous questions can stay plain strings.
6. **Ask a lot of questions.**
   - Put many narrow, independent questions about the same state into one request. They run in parallel, with no serial round trips.
   - The page says this is the best intelligence per dollar.
   - See `/patterns/fan-out` (Speculative Fan-Out) and `/cookbooks/parallel_questions`.
7. **Combine question outputs in code.**
   - Use deterministic rules or weighted sums, for example quality = 0.4·answers_request + 0.4·citations_are_supported + 0.2·(1 − contradicts_context), all using `.noul`.
   - Probabilities can also feed classical ML models as features.
   - See `/patterns/composite-scoring` and `/cookbooks/autoresearch_feature_discovery`.
8. **Route on uncertainty.**
   - Example: if `answer.confidence < 0.8`, send to human review; otherwise route on `answer.choice`.
   - Tune thresholds by plotting confidence against accuracy on your own data.
   - See `/confidence` and `/patterns/confidence-routing`.

### HTTP request body shape (from the page's JSON examples)

- **Top-level fields:**
  - `state`: string, object or array.
  - `selectedModels`: an array of model names, for example `["jev-latest"]`.
  - `questions`: an object keyed by question id (the key you read answers back with).
- **Each question object:**
  - `type`: `"noul"`, `"choice"` or `"score"`.
  - `instructions`: string or object.
  - `criteria`: optional.
- **`criteria` shape by type:**
  - Choice: an object of option key → `{what, not_for, examples}`.
  - Noul: `{true: {...}, false: {...}}`.
  - Score: an ordered array of levels `{what, signals[]}`, where index 0 is the lowest level.
- **Instruction sub-fields used in examples:** `question`, `focus`, `compare` (a list of backticked paths), `inspect` (one backticked path), plus free-form named context fields such as `potential_duplicate`.
- **CAVEAT, conflicting field names:**
  - The System One page says the `model` field selects the model.
  - This page's JSON bodies use `selectedModels: [...]`.
  - Check `/api` before implementing. The docs do not resolve which is correct.

### Python SDK (full triage example; Python only on this page)

- **Import:** `from typesafe_sdk import Choice, Noul, NoulCriteria, Score, TypeSafeClient`.
- **Constructors:**
  - `Choice(instructions=..., criteria={option: {what, not_for, examples}})`
  - `Noul(instructions=..., criteria=NoulCriteria(true={what, examples}, false={what, not_for, examples}))`
  - `Score(instructions=..., criteria=[{what, signals}, ...])`
- **Call:** `with TypeSafeClient() as client:` then `response = client.system_one(state=state, questions=questions)`.
  - Synchronous context manager.
  - No arguments shown to `TypeSafeClient()`. How it authenticates is **not stated** on this page; an env var is presumably involved but not documented here.
- **Reading results:** `response.answers[key]`, which has:
  - `.noul`: float, 0 to 1.
  - `.choice`: the option key string.
  - `.score`: float.
  - `.confidence`: float. It is shown on Choice and Score answers; that it exists on every answer is implied.
- **Flow of the triage example:**
  1. Return early without a model call if the ticket is closed.
  2. Filter orders that are not delivered in code.
  3. Build `state` with:
     - `ticket` {message, sender, links}
     - `customer` {plan, open_orders}
     - `policy` {sensitive_credentials: [password, security code, API key]}
  4. Ask seven questions in one call:
     - `topic`: Choice among billing / orders / account.
     - Noul: `requests_credentials`, `sender_identity_mismatch`, `unexpected_reward`, `refund_requested`, `mentions_open_order`.
     - `frustration`: Score with 3 levels.
  5. Compute `spam_risk` = 0.45·requests_credentials + 0.30·sender_identity_mismatch + 0.25·unexpected_reward.
  6. Send to human review if 0.4 < spam_risk < 0.6, or if topic confidence < 0.75.
  7. Quarantine if spam_risk ≥ 0.6.
  8. Otherwise route on `topic.choice`:
     - billing: pass the flag refund_requested.noul ≥ 0.7.
     - orders: pass the flag mentions_open_order.noul ≥ 0.7.
     - otherwise account support, with priority "high" when frustration.confidence ≥ 0.7 and frustration.score ≥ 1.5.
  - Speculative answers that the chosen branch does not need are simply ignored.
- **Not stated on this page:** async client, retries, timeouts, error types, rate limits, maximum questions per request, pricing per question.

Source: https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md

---

## 4. Use-case map

- **Five headline categories:**
  1. **AI automation software:** AI interleaved with reliable code that can run a million times in the background without a human co-pilot. Code, not markdown prompt files, owns control flow.
  2. **Real-time applications:** decisions at 150 ms, described as faster than human perception. Uses: games, embedding in UIs.
  3. **AI map-reduce over big data:** 100× cheaper, so very large datasets become practical. Uses: corpus search, classifying agent traces.
  4. **Universal verification:** checking prompts, extractions, reasoning traces, tool calls, or other AI inputs and outputs. Catches jailbreaks, citation errors and hallucinations at lower cost than an LLM call.
  5. **Harness engineering:** Jev queries for model routing, semantic context retrieval, LLM error detection and guardrails.
- **19 automation accordions**, each a list of short bullets:
  - Search and retrieval: semantic search instead of or alongside embeddings, relevance scoring, pairwise reranking, cross-encoding, context selection.
  - Scientific discovery.
  - Model routing.
  - LLM guardrails: input/output checks, jailbreak and injection detection, policy violations, tool-call errors, structured logging.
  - Semantic code linting in CI.
  - Feature extraction for predictive modeling.
  - Recruiting, Lead generation, Customer support, Insurance claims, Financial crime, Legal and compliance.
  - E-commerce marketplaces, Moderation and trust and safety, Advertising (including brand safety and regulatory compliance of creatives), Gaming.
  - Risk assessment, Demand forecasting.
  - Graphs and knowledge graphs: relationship classification, contradiction detection, probabilistic traversal.
- **"Example task categories" table** (task shape, when to use it, examples). Nine shapes are announced but ten rows appear:
  - Classification: one category wins.
  - Detection: probability that a property is present.
  - Scoring: an ordered rubric.
  - Routing: a category picks the code path.
  - Search: natural-language matching.
  - Retrieval: finding the most relevant context or records.
  - Ranking: semantic ordering.
  - Verification: checking an artifact for failure modes such as citation support, policy violations or tool-call errors.
  - ML feature extraction.
  - Structured data extraction: turning unstructured text into structured fields.
- **No explicit mapping** from task shapes to primitives is stated. The implied mapping would be classification/routing → Choice, detection/verification → Noul, scoring → Score, but the page does not say this.
- The page has no code, API fields, limits or pricing.

Source: https://docs.typesafe.ai/concepts/use-case-map.md
