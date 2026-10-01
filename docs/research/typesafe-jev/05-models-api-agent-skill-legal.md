# TypeSafe Jev — models, HTTP API, agent skill, legal

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

# TypeSafe docs: models, API, agent skill, Jev 1.13 jaggedness, legal

How I read them: every page was fetched with WebFetch, which runs the page through a small summarising model. I fetched several pages more than once with targeted prompts to get exact field names. The identifiers and numbers below match what came back. Where the pages are silent, I say "not stated".

## 1. What the "device" is (summary)
TypeSafe sells one hosted text-only judgment model called **Jev**. The current version is `jev-1.13.0`. It is reached through a single REST endpoint, `POST /v1/systemone`.
- You send a `state`: the content to judge, as a string, a JSON object or an array.
- You also send a map of named, typed `questions`.
- Each question gets back a probability-style answer. It is not generated text.
- There are three question primitives:
  - **Noul**: yes/no, returns a number from 0 to 1.
  - **Choice**: picks one of up to 255 options and returns a probability distribution plus a confidence.
  - **Score**: rates on an ordered rubric of 2 to 10 levels and returns a probability-weighted value.
- It is billed as a "System One" model: fast, intuitive, common-sense classification. It is not a reasoning or generation model.
- It does not accept images, audio, video or binary data. Anything visual (screenshots, pixels) has to be turned into text in code first.

## 2. Models page
Source: https://docs.typesafe.ai/models.md

**Model and aliases**
- Current versioned ID: `jev-1.13.0`. The page calls it the System One / flagship model. Endpoint: `POST /v1/systemone`.
- Alias `jev-latest` points to `jev-1.13.0`. It is the stable release and the default in the client SDKs.
- Alias `jev-preview` also points to `jev-1.13.0` right now. There is no separate preview build at the moment.
- Deprecation policy, release notes and versioning scheme: not stated.

**Pricing**
- Only input tokens are billed: USD 42 per billion input tokens, which is USD 0.042 per million.
- Output tokens are free.
- Minimums: not stated.

**Rate limits**
- 250,000 tokens per second and 1,200 requests per minute.
- Going over returns HTTP `429 Too Many Requests`.
- The SDKs retry with backoff and honour the `retry-after` header.
- The page says limits are being adjusted dynamically because of demand. Higher tiers come with enterprise plans.
- Whether limits apply per key, per account or per org: not stated clearly (the wording suggests per account).

**Context budget**
- 64k tokens per request for `state` plus all questions together.
- A separate 32k budget covers `state` plus the single longest question.
- `state` is read once and every question is evaluated against it in parallel, so state counts once, not once per question.

**Inputs**
- Text only: a string, a JSON object, or an array of text values.
- No image, audio or video input. Such content has to be converted to text before sending.

**Customization**
- There is no per-account fine-tuning. You shape behaviour per request through `state`, `instructions` and `criteria`.
- The page recommends breaking a problem into small atomic questions and combining their answers in code.

**Language**
- English is the primary training language and gives the best accuracy.
- Other languages, including CJK, work but less reliably. Test before relying on non-English workloads.

**Data**
- Customer requests and responses are not used for training.
- Zero data retention (ZDR) is available to enterprise customers under the Data Processing Agreement.

**Latency:** no millisecond figures are given anywhere. The model is only described as "fast".

## 3. API reference
Source: https://docs.typesafe.ai/api.md

Page headings: Evaluation endpoint, Request body, Question types (Noul / Choice / Score), Response body, Answer types (Noul / Choice / Score answer), Errors, Handling rate limits.

**Endpoint and auth**
- `POST https://api.typesafe.ai/v1/systemone`
- Headers: `Authorization: Bearer <API_KEY>` and `Content-Type: application/json`.
- API keys are created at https://console.typesafe.ai/keys (from the agent-skill page).
- Other headers (versioning, request-id, idempotency): not stated.
- Streaming, async mode, batching endpoint, pagination, timeouts: not stated. The call is a single synchronous request and response.

**Request body (all three fields required)**
- `state`: string, object or array. This is the content being evaluated.
- `model`: string. The docs use `"jev-latest"`.
- `questions`: a map from your own question ID to a Question object. Limits on the number of questions, the ID format or the state size in bytes: not stated. The only size limit is the token budget on the models page.

**Question objects** (every one has `type` and `instructions`)
- **Noul** (`type: "noul"`)
  - `instructions` (string, object or array) is required.
  - `criteria` is optional. It is an object with optional keys `"true"` and `"false"`, each a string, object or array describing when the answer should be true or false.
- **Choice** (`type: "choice"`)
  - `instructions` is required.
  - `criteria` is required. It maps each option name (string) to a rubric: string, object, array or `null`.
  - At most 255 options per Choice.
- **Score** (`type: "score"`)
  - `instructions` is required.
  - `criteria` is required. It is an ordered array of level descriptions (string, object or array).
  - At least 2 levels; the API accepts up to 10.

**Structured instructions**
- `instructions` can be an object instead of a string. You put the question in one field and data in the other fields.
- Inside the question text, you refer to those data fields by name in backticks. The docs example has an object containing a `potential_duplicate` record (name / location / last_employer) and a `question` field that mentions `potential_duplicate` in backticks.
- The docs say this is the same way you point a question at a nested `state` value. They give no worked example of the nested-state syntax (for example a dotted path), so the exact path syntax is not stated.

**Response body**
- `model`: the resolved versioned ID, for example `"jev-1.13.0"` even when you sent `jev-latest`.
- `answers`: a map with the same IDs you used in `questions`, one answer per question.
- `usage`: `{input_tokens: int, output_tokens: int}`. The example shows 296 input tokens and 20 output tokens for a one-question request with a one-sentence state.

**Answer shapes**
- Noul answer: `{type:"noul", noul: <0..1>}`. The example value is 0.95 for "is_urgent" on a ticket about payouts failing for 3 days.
- Choice answer: `{type:"choice", choice:"<option>", probabilities:{<option>: p, ...}, confidence: <0..1>}`. Example: billing 0.88 / technical 0.12 / sales 0.0, confidence 0.81.
- Score answer: `{type:"score", score:<float>, legend:{"0":"desc", ...}, probabilities:{"0":p, ...}, confidence:<0..1>}`.
  - Example: legend Calm / Frustrated / Very angry, probabilities 0.0 / 0.95 / 0.05, score 1.05, confidence 0.92.
  - The keys are level indexes as strings.
  - `score` is probability-weighted, so it can fall between levels.
- `confidence` is derived from the answer's probability distribution. The exact formula is not stated. The example numbers suggest it is not simply the maximum probability (0.88 gave 0.81 and 0.95 gave 0.92).

**Errors**
- `401 Unauthorized`: key missing or invalid.
- `422 Unprocessable Entity`: the request failed validation.
- `429 Too Many Requests`: rate limited.
- `529 Overloaded`: the service is overloaded.
- The JSON shape of an error body: not stated.
- Retry `429` and `529` with exponential backoff. The SDKs do this automatically and, per the models page, honour `retry-after`.

## 4. SDK (only seen in the jaggedness page example)
Sources: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md and https://docs.typesafe.ai/models.md

**Python**
- Module `typesafe_sdk`, which exports `TypeSafeClient` and `Noul`.
- The client is built with `TypeSafeClient(model="jev-1.13")`. Note that the example uses `jev-1.13`, not the full `jev-1.13.0` ID.
- API-key handling in the constructor is not shown; presumably it reads `TYPESAFE_API_KEY`, but that is not stated.
- The call is `client.system_one(state_dict, questions_dict)`, both positional. `questions_dict` maps IDs to `Noul(instructions=...)`.
- Results are read as `result.nouls["<id>"].noul`. So the result groups answers by type, with a `nouls` map; the attribute names for choices and scores are not stated.

**Other details**
- The pip package name, TypeScript/JS SDK and install commands: not stated in these pages.
- The models page confirms that client SDKs exist and default to `jev-latest`.

## 5. Jev 1.13 jaggedness (strengths and failure modes)
Source: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md

The page was last reviewed on 2026-09-17.

**Strengths**
- Fast, calibrated, good at common-sense judgment.
- Gives very consistent, quantitatively similar outputs for semantically similar inputs.
- Best at System One tasks.

**Stated weaknesses**
- Tasks that need extra levels of indirection.
- Quite literal reading.
- Anything that needs numeric precision.

**Failure modes, by page heading**
1. **Literal reading.** Scoping words, negations and implied conditions are taken at face value. Fix: state the exact condition in `instructions`, put boundary cases in `criteria`, or split one ambiguous question into two literal ones and combine them in code.
2. **Math and Numbers**, which has three sub-sections:
   - **Counting**: counting characters, occurrences or list items is unreliable, and the error grows with size. Fix: ask one Noul per item and add up the results in code. The docs example does this for an 8-item list, asking "is items[i] a fruit" and counting items where `noul > 0.5`. The comment says the threshold is your choice.
   - **Numeric representations**: hex colours, RGB triples, and assembly or binary do worse than English names or high-level text. Fix: convert in code and pass computed values or named buckets. Keep the model for real judgments such as "does this colour read as a warning".
   - **Math using score**: exact numbers cannot be rebuilt by interpolating between score levels, because calibration between levels is weak. Use score only to check whether a threshold is passed.
3. **Date and time comparison.** Dates are read as text, not as ordered quantities. Ordering, distances and window checks are unreliable, and worse with mixed formats, relative dates or quarters. Fix: extract date parts with Choice over enumerated options and do the arithmetic in code.
4. **Indirection.** Double negatives, multi-hop questions and property-of-property questions lose accuracy. Fix: write instructions directly and name the relevant `state` field.
5. **Large state full of irrelevant detail.** Unrelated content distracts the model ("context rot"), and accuracy drops as state grows. Fix: filter in code and send only the fields you need. A Noul can be used first as a relevance filter.
6. **Adversarial content.** Data is not treated as hostile by default, so injected instructions, misleading framing or self-arguing text can steer answers. The only mitigations given are explicit criteria and thorough testing before deployment.
7. **Contradictory instructions and criteria.** Accuracy drops when the two conflict. Counter-intuitive mappings, such as true meaning "no", do worse. Fix: keep them aligned and treat criteria as an extension of the instructions.
8. **Common-sense structural invariants.** Two examples:
   - The ticket "not happy with the fit, what are my options" asked "is the customer asking for a refund?" gives Noul 0.22, but Choice gives yes 0.01 / no 0.99 with confidence 0.97.
   - The ticket "charged twice, can someone look" gives 0.72 for the refund question and 0.47 for its negation, which sum to 1.19.
   - Lessons: a Noul and its negation do not sum to 1. Noul is absolute and Choice is relative, so they are not comparable. Thresholds tuned on one primitive should not be reused on another. Do not expect answers to satisfy arithmetic identities.
9. **Generation.** The model is not trained to generate text, and forcing it to by chaining choices is slow and ineffective. Use Choice over bounded options. For open-ended output, use regex or a generative model.

**Things the page says to avoid**
- Asking what code can compute exactly.
- Packing several judgments into one question.
- System Two tasks with layered indirection.
- Putting more context in `state` than the question needs.

**Not covered:** determinism (same input giving the same output), HTML/DOM inputs and image inputs.

## 6. Agent skill
Source: https://docs.typesafe.ai/agent-skill.md

**Installing**
- Claude Code: `claude plugin marketplace add typesafe-ai/skills`, then `claude plugin install typesafe@typesafe-ai`. Invoke it with `/typesafe:typesafe-ai`.
- Other agents: `npx skills add typesafe-ai/skills --skill typesafe-ai`, with `-g` for a global install.
- Manual: copy the `skills/typesafe-ai` directory from https://github.com/typesafe-ai/skills/tree/main/skills/typesafe-ai.
- The skill file is at https://raw.githubusercontent.com/typesafe-ai/skills/main/skills/typesafe-ai/SKILL.md.

**Updating**
- Claude Code: `claude plugin marketplace update typesafe-ai` and `claude plugin update typesafe@typesafe-ai`, then `/reload-plugins`, or turn on auto-update in `/plugin`.
- Other agents: `npx skills update`.

**Other resources**
- Environment variable: `TYPESAFE_API_KEY`, used when you want the agent to run cheap test queries. Keys come from https://console.typesafe.ai/keys.
- Cookbooks: https://console.typesafe.ai/docs/cookbooks.
- Docs index: https://docs.typesafe.ai/llms.txt.

**Guidance**
- Talk the plan through with the agent first and review it before any code is written.
- Keep all question definitions and thresholds in one file.
- Check the agent's assumptions rather than accepting them.

**Common issues**
- If routing misbehaves, tune the question wording and the thresholds. Thresholds set too high give false negatives; too low gives false positives.
- To pick the best option, compare the options' values directly instead of putting a confidence threshold on everything. Use probabilities for statistical or precision work.
- If the agent invents request or response fields, the skill install is stale. Update it.

## 7. Legal
Source: https://docs.typesafe.ai/legal.md

- The page links three documents:
  - Data Processing Agreement: https://typesafe.ai/legal/data-processing
  - Master Customer Agreement: https://typesafe.ai/legal/mca
  - Privacy Policy: https://typesafe.ai/legal/privacy-policy
- The Privacy Policy includes a commitment not to train models on user data.
- For enterprise zero data retention, contact sales@typesafe.ai.
- Not on this page: retention periods, acceptable-use terms, liability, licensing and effective dates. Those would be in the linked documents, which were not part of this group.

## 8. What this means for a tag-checking implementation
These are my own conclusions, not claims from the docs.
- Deterministic comparisons have to stay in code: tag ID ("bn") equality, size strings like 300x250, counts and dates. The docs say plainly that Jev is weak at counting, numbers, hex values and dates.
- Jev fits fuzzy, text-only judgments where the answer is bounded. Examples:
  - Which placement category a tag's surrounding text matches (Choice).
  - Whether a creative's alt text or landing copy fits the brief (Noul).
  - Sorting an error message into a category (Choice).
- Send only the fields a question needs, because irrelevant detail costs accuracy.
- Treat publisher page content as potentially adversarial, since the model does not guard against injected instructions.
- Screenshots cannot be sent; turn anything visual into text in code first.
- Keep all questions and thresholds in one constants module.
- Store the resolved `model` value from each response for auditability.
