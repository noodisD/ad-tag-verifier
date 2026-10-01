# Research: TypeSafe Jev and jev-ultrafast

Notes taken on 2026-10-01 to answer one question: *would Jev, or browser-use's
`jev-ultrafast`, make this project more efficient?* The answer and the plan are in
[jev-integration-proposal.md](jev-integration-proposal.md). The rest of this folder
is the reference it rests on.

All notes are in our own words and carry their source URLs. They are a working
reference, not a mirror: the documentation belongs to TypeSafe and is not ours to
republish. `jev-ultrafast` itself is MIT licensed.

## What is here

| File | Covers |
|---|---|
| `typesafe-jev/01-introduction-and-quickstart.md` | what Jev is, the request/response shape, first calls |
| `typesafe-jev/02-concepts-and-state.md` | System One, what goes into `state`, what Jev is good and bad at |
| `typesafe-jev/03-primitives-choice-score-noul.md` | the three question types and their limits |
| `typesafe-jev/04-confidence-and-patterns.md` | confidence semantics, routing and fan-out patterns |
| `typesafe-jev/05-models-api-agent-skill-legal.md` | model versions, API reference, limits, data-handling terms |
| `typesafe-jev/06-python-sdk.md` | `typesafe-sdk`: clients, retries, timeouts, changelog |
| `jev-ultrafast/01-readme-performance-agents.md` | README, performance report, AGENTS.md |
| `jev-ultrafast/02-browser-snapshot-and-driver.md` | how it drives Chrome and describes a page |
| `jev-ultrafast/03-examples-tests-scripts.md` | examples, tests and scripts |
| `jev-ultrafast/04-core-loop.md` | the agent loop and the two-question request |

## What was **not** read

Say this plainly, because "the full documentation" would be false:

| Not read | Why | Does the proposal depend on it? |
|---|---|---|
| 21 pages of TypeSafe cookbooks and demos (`/cookbooks.md` and 18 recipe pages, `/demos.md`, `/demos/smart-home.md`) | The company's web gateway answered every request with a redirect to its URL-filter override page. The redirect was not followed: getting past a URL filter is a decision for whoever administers it. | No. Nothing in the proposal relies on a cookbook. |
| The JavaScript SDK type reference (about 60 pages) | Skipped on purpose: this project is Python. The Python SDK was read in full. | No. |
| `jev_ultrafast/agent.py`, `model.py`, `questions.py` line by line | A reading agent declined the task by mistake. They were read afterwards through a summarising fetch, so exact numbers are "reported" rather than verified. | Only for the borrowed principles; see `04-core-loop.md`. |

If a cookbook turns out to matter (the re-ranking and hierarchical-classification
recipes are the likeliest), allow-list `docs.typesafe.ai` or paste the pages and
the notes can be extended.

## One more fact about reachability

From the development machine, a direct TLS connection to `api.typesafe.ai` fails at
the certificate-revocation check (`CRYPT_E_NO_REVOCATION_CHECK`). That is a
property of this network, not of TypeSafe. It was **not** worked around — disabling
revocation checking would switch off a protection. Whether the API is reachable
from the machines this tool runs on is therefore unconfirmed, and is the first thing
to settle before any Jev work (see the proposal's preconditions).
