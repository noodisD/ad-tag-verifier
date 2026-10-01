# TypeSafe Jev — the three question types

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

## Primitives overview (Questions)

TypeSafe's "System One" API asks the model for fast, one-glance judgments over a `state`. There are three question types, which are the only primitives:

| type | Use it when | Answer fields |
|---|---|---|
| `choice` | one option from an unordered fixed set | `choice`, `probabilities`, `confidence` |
| `score` | a position on an ordered spectrum of describable levels | `score`, `legend`, `probabilities`, `confidence` |
| `noul` | a single yes/no proposition | `noul` (float 0..1, P(yes)) |

What a question contains:
- **ID**: a key the caller chooses (e.g. `refund_requested`). Answers come back under this key. The Choice page says the model never sees the ID.
- `type`: `choice` | `score` | `noul`.
- `instructions`: the question asked about the state.
- `criteria`: for Choice, a map of option name to description. For Score, an ordered array of levels. For Noul, an optional `{true, false}` object.

Answers are constrained. Each one is a probability distribution over the options or levels the caller supplied, and the docs say no value outside them is ever returned.

**Design guidance (paraphrased):**
- Ask for a judgment a knowledgeable person would make in about a second. "Analyze this and decide the best action" is the wrong kind of question. Split it into several questions and combine the answers in code.
- **Batch**: put every question that shares the same state in one request. Types can be mixed. The model evaluates questions in parallel. Extra questions barely change latency and cost only their own tokens, which the docs call cheap.
- **Speculative fan-out**: ask every question your code *might* need and ignore the answers that turn out not to matter. A cookbook claim: 13 questions batched in one call was 11.5x cheaper and 9.6x faster than 13 separate calls, with the same answers.
- **Independence**: questions in one request cannot see each other's answers. Make a second request only when:
  - you cannot build it without the first answer,
  - you need to fetch more data based on the first answer, or
  - the options offered depend on an earlier answer.

  The docs call two requests "the exception". Their examples of legitimate two-step flows:
  - skill suggestion: rank 182 skills, then re-judge the full text of the top 3,
  - structure recovery,
  - hierarchical classification.
- **Field references**: when the state is a JSON object, name the field in `instructions` as a dot-and-index path wrapped in backticks, e.g. `` `ticket.messages[0].text` `` or `` `order.charges` ``. `state` may be a plain string or a nested JSON object. Maximum state size: not stated.
- The Python SDK sample imports `Choice, Noul, Score, TypeSafeClient` from `typesafe_sdk`, uses `with TypeSafeClient() as client:` and calls `client.system_one(state=..., questions={...})`. Answers are read as `response.answers[id].noul`, `.choice` or `.score`.
- Not stated on this page: model names, rate limits, a limit on questions per request, pricing, latency figures, error codes.
- Links: `/concepts/system-one`, `/concepts/state`, `/sdk`, `/patterns`, `/confidence`, `/patterns/fan-out`, `/patterns/composite-scoring`, and cookbooks `parallel_questions`, `skill_suggestion`, `autoformat`, `hierarchical_classification`. Doc index: `https://docs.typesafe.ai/llms.txt`.

Source: https://docs.typesafe.ai/primitives.md

## Choice

**Request.**
- Endpoint: POST `https://api.typesafe.ai/v1/systemone`. Top-level body: `state`, `model` (e.g. `"jev-latest"`), `questions` (map of ID to question).
- Question shape: `{type:"choice", instructions, criteria:{optionName: description}}`.
- The model sees both option names and descriptions, so the descriptions should tell the options apart.
- Up to **255 options** per Choice. Whether exceeding that returns an error: not stated.
- Add `other` or `none of the above` when the list may not cover every input.
- Minimum option count: not stated. Rules on key characters or duplicate keys: not stated.

**Response.** Top level is `{model:"jev-1.13.0", answers:{...}, usage:{input_tokens, output_tokens}}`. The response names the resolved model version even though the request said `jev-latest`. Example: 328 input and 34 output tokens.

The Choice answer is `{type:"choice", choice, confidence, probabilities:{opt: p}}`:
- `choice` is the highest-probability option. Tie-breaking: not stated.
- `probabilities` sum to 1.0.
- `confidence` (0..1) reflects the shape of the distribution: a single peak is high, a flat spread is low. The exact formula is not stated on this page; it links to `/confidence`.

**Worked triage example.** State: shoes arrived late, in the wrong size, with a double charge. Five speculative questions:

| Question ID | Options | Answer |
|---|---|---|
| `department` | returns / shipping / billing | returns, conf 0.42 (p: returns 0.61, billing 0.35, shipping 0.04) |
| `return_reason` | wrong_size, wrong_item, damaged, changed_mind, other | wrong_size, conf 1.0 |
| `shipping_issue` | not_delivered, delayed, wrong_address, damaged_in_transit, other | delayed, conf 0.67 |
| `requested_resolution` | exchange, refund, replacement, information | refund, conf 0.2 |
| `tone` | calm, frustrated, angry | frustrated, conf 0.76 |

The sample code logic:
- department confidence < 0.3: send to manual triage;
- otherwise route by `department.choice`;
- notify a secondary team when its probability > 0.25;
- resolution confidence < 0.5: ask the customer;
- angry tone: escalate to a senior agent.

**Structured criteria.**
- An option's value can be an object with user-chosen keys such as `what`, `not_for` and `examples`. These key names are not reserved; the model reads both keys and values.
- Example: `return_policy` versus `return_status`, told apart by `not_for`.

**Deep taxonomies.** Chain one Choice per level. The Hierarchical Classification cookbook runs a beam search over the Choice probabilities rather than following a single greedy path.

**SDK.** `Choice(instructions=..., criteria={...})`, read with `response.answers["department"].choice`. A TypeScript SDK is not mentioned.

Source: https://docs.typesafe.ai/primitives/choice.md

## Score

**Request.**
- Question shape: `{type:"score", instructions, criteria:[level0, level1, ...]}`.
- The array is ordered from low to high and must have **2 to 10 levels**. What happens outside that range: not stated.
- A level's number is its array index, 0 to N-1.
- The model sees only each level's description. It judges each level independently against the state and never sees the level numbers or the neighbouring levels. So a description like "worse than the previous one" does not work.

**Response.** Answer shape: `{type:"score", score, confidence, legend:{"0":desc,...}, probabilities:{"0":p,...}}`.
- In JSON, `probabilities` and `legend` are keyed by level number as a string. The Python SDK's typed `ScoreAnswer` keys them by integer.
- `score` is the expected level, `sum(level * p)`. It can fall between levels. Example: 0×0.0 + 1×0.57 + 2×0.43 = 1.43.
- `confidence` is 1.0 when all probability sits on one level and gets lower the more evenly it spreads. The formula links to `/confidence`.
- Example usage: 332 input and 18 output tokens. Model `jev-1.13.0`.

**Reading a score.**
- A fractional score means the model split between levels. Low confidence usually points to overlapping levels, a question covering more than one dimension, or too little information in the state.
- Fractional scores work well for ranking. Round to the nearest level when you need a discrete outcome; the `entity_alignment` cookbook does this.

**Writing levels.**
- Describe concrete situations rather than degrees ("moderately severe" is too vague).
- Each level must make sense on its own.
- One dimension per question.
- Give extreme cases that need different handling their own level.
- Validate against labelled data; confidence alone does not show the levels are good.

**Composite scoring.**
- Ask several Score questions in one request, normalise each as `score / (len(criteria) - 1)`, then take a weighted sum in code.
- Example: `severity` (3 levels), `frustration` (3 levels) and `report_quality` (4 levels), combined as `0.6*sev + 0.3*frus + 0.1*quality`. See `/patterns/composite-scoring`.

**Structured levels.** A level can be an object, e.g. `{what, examples:[...]}`. Use the same keys on every level. Examples help only when they resemble real inputs.

**SDK.** `Score(instructions=..., criteria=[...])` passed to `client.system_one`. TypeScript: not mentioned. Auth and headers: not stated on this page.

Source: https://docs.typesafe.ai/primitives/score.md

## Noul

**Request.** Question shape: `{type:"noul", instructions, criteria?:{true: desc, false: desc}}`.
- `criteria` is optional. Without it the model relies on `instructions` alone. Adding `true`/`false` descriptions sharpens boundaries for subtle cases.

**Response.** Answer shape: `{type:"noul", noul: 0.99}`.
- The single value combines the answer and the certainty. Near 1 is yes, near 0 is no, near 0.5 is unsure.
- There is **no confidence field**, because the distribution has only two outcomes.
- Example: two Nouls cost 360 input and 39 output tokens with `jev-1.13.0`. On human-escalation test messages, values ranged from 0.02 to 0.99.

**Thresholds.** Pick them by the cost of each kind of error:
- 0.5 when both errors cost the same;
- higher (e.g. 0.9) when false positives are costly, such as paging someone;
- lower when false negatives are costly, such as missing a safety issue.

The routing example uses `YES = 0.8` and `NO = 0.2`:
- if either Noul is between NO and YES, send the message to human review;
- otherwise priority is high when the repeat-contact Noul > YES;
- then route to an agent if the wants-human Noul > YES, else to the bot.

**Writing Nouls.**
- One proposition per Noul. Split compound "A and B" questions.
- Phrase the question so that a high value means yes (e.g. "contains personal data" rather than "is free of it").
- Both question and statement phrasing work.

**Structured instructions.** `instructions` can be an object holding the question plus data, e.g. `{potential_duplicate:{name, location, last_employer}, question:"...`potential_duplicate`?"}`. Code can generate one such Noul per candidate record; the example returns 0.74, 0.09 and 0.08.

**Batching.** Asking many Nouls in one request, one per checklist condition, barely changes latency.

**Cookbooks:**
- `parallel_questions`: a 13-question regulatory checklist.
- `consistency_noul_cookbook`: a 15-question rubric, checking how stable values are across runs.
- `rerank_typesafe`: one Noul per query–candidate pair, sorted by the value itself rather than a threshold.
- `semantic_find`: a Choice finds the line, and a Noul checks whether an answer exists at all.
- `autoformat`: one Noul per pair of lines, to rebuild paragraphs.

**SDK.** `from typesafe_sdk import Noul, NoulCriteria, TypeSafeClient`, then `Noul(instructions=..., criteria=NoulCriteria(true=..., false=...))`, read with `.noul`.

Not stated: auth headers, curl examples, the origin of the name "Noul", a TypeScript SDK.

Source: https://docs.typesafe.ai/primitives/noul.md

## Advanced: structure

These four fields accept any JSON value (string, object, array or null, called `EntryType`):
- `instructions` (all three types);
- Choice `criteria` values;
- Score `criteria` entries;
- Noul `criteria.true` and `criteria.false`.

The docs say System One models are trained to understand structure. Structure a question for clarity in multi-part questions, or when your data (a schema, a taxonomy, a DB row) is already JSON.

**Patterns shown (request shapes only; no responses shown):**
1. **Invoice validation.** State `{source_text}`. Each question's `instructions` is `{field:{name,type,unit?,description}, extracted_value?, question}`, sharing one `field` shape. Four questions use it:
   - a Noul checks the extracted value;
   - a Choice's `criteria` holds candidate strings whose values are **null**, so null option descriptions are valid;
   - two Scores use ranged levels: amount bands, and payment terms (Due on receipt / Net 10 / 30 / 60 / 90).
2. **Support routing.** Choice `instructions` is `{question, focus}`. Each option is `{what, not_for, examples:[...]}`.
3. **Taxonomy walk.** Choice option values are nested subtrees (objects or arrays of child category names), so the model can look inside a branch before picking it. Walk one level per request in code. If probabilities are uncertain, explore several branches.
4. **PR scope.** Score levels are `{summary, signals:[...]}` and `instructions` is `{question, note}`.
5. **Phishing.** State is `{sender:{display_name,email}, message}`. Noul `instructions` is `{question, inspect, focus}`. `criteria.true` and `criteria.false` are each `{what, examples}`.

Array-valued instruction keys are also shown, e.g. `compare: ["ticket.sender.display_name","ticket.sender.email"]` alongside a `focus` string.

**Caveat on the model key.** The page's `TypesafeExample` React component writes the examples with `selectedModels:["jev-latest"]`. That is the key in its playground share payload, not the API body; the API pages use `model`.
- The component compresses the payload with LZ-string `compressToEncodedURIComponent` and links to `https://console.typesafe.ai/decode#share/<compressed>`.
- The payload fields are `apiVersion:"v1"`, `documentText`, `promptsText` and `selectedModels`.

Source: https://docs.typesafe.ai/primitives/advanced.md
