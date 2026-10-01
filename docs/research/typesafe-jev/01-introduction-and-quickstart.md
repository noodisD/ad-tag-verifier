# TypeSafe Jev — introduction and quick start

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

## 1. What TypeSafe / Jev is (Introduction)

- The product is a model named **Jev**, which TypeSafe calls a "System One" model. It does not generate text for people to read. You send it a **state**, which is the input text, plus a set of **typed questions**. It sends back structured, typed answers that code can branch, sort or route on directly, so no text has to be parsed.
- The page includes a flow diagram (Mermaid): Input (state + questions) → model checks each question in parallel → Output (typed answers + probabilities + confidence) → your code (branch/sort/route).
- **Parallel and isolated:** every question is checked against the same state on its own, and all of them run in one request. The docs say adding questions barely changes response time. They also say more questions do not cause "context-rot", because each question is evaluated on its own.
- **Three primitives (question types):**
  | Primitive | Purpose | Output fields |
  |---|---|---|
  | Choice | pick one option from a set | `choice`, `probabilities`, `confidence` |
  | Score | rate against an ordered rubric | `score`, `probabilities`, `confidence` |
  | Noul | is this statement true? | `noul` (a number 0–1) |
- **Confidence** comes back only for Choice and Score. Noul returns just the 0–1 value, with no confidence field. Your code uses confidence to decide whether, and how, to act on an answer.
- **Design guidance:** keep each question atomic, with one concern per question. Split a complex judgement into several questions and combine the results in application code, for example with a weighted sum. When priorities change, you change a coefficient in code instead of rewriting a prompt.
- These pages do not define exactly what Noul 0 and Noul 1 mean. The sensible reading is 0 = false and 1 = true.
- Pages linked from here: /concepts/system-one, /primitives, /primitives/choice, /primitives/score, /primitives/noul, /confidence, /patterns, /introduction/quickstart, /introduction/machine-learning-primer, plus the llms.txt index.
- Latency figures (ms), pricing and rate limits: not stated on this page.

Source: https://docs.typesafe.ai/introduction.md

## 2. Quick start: Playground, HTTP API, Python SDK, agent skill

Page sections in order: "Try it: the Playground", "Call it: the API", "Code it: the Python SDK", "Vibe it: the agent skill".

### Playground
- URL: https://console.typesafe.ai/playground. There are 4 numbered steps: open the playground, paste text as the state, add a Noul question, then add more questions of mixed types (Choice/Score).

### HTTP API
- **Endpoint:** `POST https://api.typesafe.ai/v1/systemone`
- **Headers:** `Authorization: Bearer $TYPESAFE_API_KEY` and `Content-Type: application/json`. You create keys at https://console.typesafe.ai/keys.
- The example curl sends the JSON body through a quoted heredoc (`-d @- <<'EOF'`).
- **Request body shape:**
  - `state`: string. The input text. Example: a support message about a Stripe integration that has been failing for 3 days, asking for urgent help.
  - `model`: string. Example value `"jev-latest"`. The page does not say whether this field is required or optional. The SDK uses `jev-latest` by default.
  - `questions`: an object whose keys are names you choose (for example `department`, `frustration`, `is_urgent`). Each value is a question object:
    - `type`: one of `"choice"`, `"score"`, `"noul"`
    - `instructions`: string, the question or statement in natural language
    - `criteria`:
      - for **choice**, an object that maps each option label to a description. Example: `billing` → payment/subscription issues, `technical` → bugs/integration problems, `sales` → pricing/account questions.
      - for **score**, an ordered array of rubric level descriptions from low to high. Example: calm → frustrated but civil → very angry.
      - for **noul**, no criteria; only `instructions`. Example: a statement that the message conveys urgency.
- **Response body shape:**
  - `model`: the concrete version that ran. The example asked for `jev-latest` and got back `"jev-1.13.0"`.
  - `answers`: an object with the same keys as `questions`. Every answer has a `type` field.
    - choice answer: `choice` (the chosen label, a string), `confidence` (a number), `probabilities` (an object mapping every option label to a probability). Example: `choice: "technical"`, `confidence: 0.78`, `probabilities: {technical: 0.85, sales: 0.0, billing: 0.15}`. Here confidence (0.78) is **not** the same as the top probability (0.85). The pages do not explain how confidence is computed; see /confidence.
    - score answer: `score` (a number), `confidence`, `probabilities` keyed by the string index of each rubric level (`"0"`, `"1"`, `"2"`), and `legend`, which maps each string index to its rubric text. Example: `score: 1.0`, `confidence: 1.0`, `probabilities: {"0":0.0,"1":1.0,"2":0.0}`. So the score is on a **0-based index scale** over the criteria array, and `1.0` means the middle level ("frustrated but civil"). The docs do not say whether the score is a probability-weighted expected index or the argmax index.
    - noul answer: `noul` (a number 0–1). Example `1.0`. No confidence and no probabilities.
  - `usage`: `input_tokens`, `output_tokens`. Example: 392 input and 65 output tokens for 3 questions.
- Errors, status codes, rate limits, timeouts, pricing and latency: none are mentioned on this page (not stated). The page points to https://docs.typesafe.ai/api for the full API reference.

### Python SDK
- Package: `typesafe-sdk`. Install with `pip install typesafe-sdk` or `uv add typesafe-sdk`. Requires Python >= 3.10.
- Import: `from typesafe_sdk import Choice, Noul, Score, TypeSafeClient`
- `client = TypeSafeClient()` reads the `TYPESAFE_API_KEY` environment variable and uses model `jev-latest` by default.
- Question constructors: `Choice(instructions=..., criteria={label: description, ...})`, `Score(instructions=..., criteria=[level0, level1, ...])`, `Noul(instructions=...)`.
- Call: `response = client.system_one(state=..., questions={"key": Choice(...), ...})`
- Reading results: `response.answers["department"].choice`, `response.answers["frustration"].score`, `response.answers["is_urgent"].noul`. The answer objects are typed attribute objects.
- These pages do not say whether an async client, retries or timeout parameters exist. For those, see https://docs.typesafe.ai/sdk.

### Agent skill
- Claude Code: `claude plugin marketplace add typesafe-ai/skills`, then `claude plugin install typesafe@typesafe-ai`.
- Other agents: `npx skills add typesafe-ai/skills --skill typesafe-ai`.
- Skill source file: https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md (raw: https://raw.githubusercontent.com/typesafe-ai/skills/main/skills/typesafe-ai/SKILL.md). The page then tells you to ask your coding agent to use the TypeSafe skill while you build. More detail is at https://docs.typesafe.ai/agent-skill.

Source: https://docs.typesafe.ai/introduction/quickstart.md

## 3. Jev with coding agents: what it is not

- Jev does **not** replace the LLM behind a coding agent (Claude Code, Cursor). It cannot generate text, write code, hold a conversation, stream text, call tools, or edit files from natural-language instructions.
- It works **alongside** your app's code as a component that makes structured decisions: a `choice` with probabilities, a `score` on a rubric, or a `noul` (0–1) for a true/false statement.
- The docs suggest using it for:
  - routing requests with a confidence value
  - rubric scoring, such as urgency, quality or risk
  - checking statements about documents or messages
  - replacing fragile prompts that return JSON which you then parse
- A table on the page points each goal to a next step:
  - To make an agent write better TypeSafe code, install the agent skill.
  - To build Jev into an app, start with Quick start, then read /concepts/how-to-build-with-system-one and /patterns.
  - To swap the agent's own model, Jev is the wrong tool; keep your agent's model.
  - To try it without code, use the Playground.
- Links: /concepts/system-one, /concepts/state, /primitives, /agent-skill, /patterns, /patterns/confidence-routing, /patterns/intent-routing, /introduction/quickstart, /concepts/how-to-build-with-system-one, and the playground.

Source: https://docs.typesafe.ai/introduction/coding-agents.md

## 4. ML primer: RLCD and calibration (background, no API detail)

- The page describes TypeSafe's approach as "Machine Native Intelligence". The goal is software-like properties: structure, reliability, observability, testability, speed, consistency and low cost. It expects automation to be about 99% machine-to-machine and 1% human interaction. There is a section titled "Building prod, not God".
- The page compares three post-training approaches:
  - **RLHF** makes chat models whose answers people prefer. The page notes that TypeSafe cofounder Diogo Almeida co-invented RLHF.
  - **RLVR** (verifiable rewards) makes reasoning models that are strong at maths and reasoning, but slower and more expensive.
  - **RLCD** (Reinforcement Learning for Calibrated Decisions) is TypeSafe's own approach. The model outputs a decision plus a calibrated probability, not generated text.
- **Output contract:** a higher probability should mean a higher chance the answer is correct. Calibration means that outcomes given 0.2 happen about 20% of the time, those given 0.8 about 80% of the time, and those given 1.0 essentially always. That is why the docs treat the probabilities as usable thresholds in code.
- Problems the page attributes to RLHF:
  - **sycophancy**: the model is rewarded for sounding confident, including confident hallucinations
  - **mode dropping**: preference tuning narrows the output distribution, likened to mode collapse in GANs
- The page gives no architecture details, such as a single forward pass or any sampling method (not stated). It gives no dataset or benchmark numbers (not stated).
- Links: https://typesafe.ai/manifesto, /confidence.

Source: https://docs.typesafe.ai/introduction/machine-learning-primer.md

## 5. What this means for an implementation (caveats)

- **Calls:** each call is one synchronous HTTP POST that can carry many named questions against one state. Batching many atomic questions into one call is the intended pattern.
- **Thresholds:** for Choice and Score, gate actions on `confidence` or `probabilities`. For Noul, gate on the raw `noul` value, because it has no confidence field.
- **Model version:** pin or log the `model` value that comes back (for example `jev-1.13.0`), because `jev-latest` is an alias.
- **Score index:** `score` is on a 0-based index over the criteria array, not a 1–N scale. Use `legend` to turn an index back into its rubric text.
- **Not covered on these pages:** error codes, retries, rate limits, pricing, latency numbers, limits on state length or question count, and whether an async API exists. Look for them on /api, /sdk and /confidence.

Source: https://docs.typesafe.ai/introduction/quickstart.md
