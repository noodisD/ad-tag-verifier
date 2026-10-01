# TypeSafe Jev — Python SDK

> **Research notes, 2026-10-01.** Written in our own words from the pages
> listed under each "Source:" line — a technical reference, not a copy of the
> documentation. The authoritative text is at the source URL. Anything marked
> "not stated" was not stated in the source. Read for the Ad Tag Verifier
> project; see [../README.md](../README.md) for what was and was not read.

# TypeSafe Python SDK (`typesafe-sdk`): technical reference

All 12 pages loaded. I read them through WebFetch's summarizer, which does not return raw markdown. Where two summaries disagreed, I fetched the page again with narrower questions. The resolved answer is recorded below.

## 1. Package, install, auth
- The PyPI and uv package is `typesafe-sdk`. Install with `uv add typesafe-sdk` or `pip install typesafe-sdk`. The import root is `typesafe_sdk`.
- Source repo: GitHub `typesafe-ai/typesafe-sdk-python`.
- Supported Python versions: not stated. License: not stated. Dependencies are not listed on the page. The API docs show **pydantic** (the ser/de library since v0.7.0) and **`httpx2`** (not `httpx`; all transport, client, timeout and response types are `httpx2.*`).
- Auth uses an API key from the `TYPESAFE_API_KEY` env var or the `api_key=` argument. Keys are created at console.typesafe.ai. The header name and format (Bearer or other) are not stated. The docs only say that auth, SDK-identification and `Accept` headers cannot be overridden.
- API-key validation runs when the client is constructed, before any request or retry. Leading and trailing whitespace and newlines are stripped. An empty env value is ignored. The client rejects a key that is empty or contains internal whitespace, control characters or non-ASCII characters, and raises `TypeSafeError`. Since v0.7.1 the key value is kept out of logged exceptions.

Source: https://docs.typesafe.ai/sdk/python.md , https://docs.typesafe.ai/sdk/python/usage.md , https://docs.typesafe.ai/sdk/python/api/clients/sync.md

## 2. Quickstart shapes
- **Sync:** construct `TypeSafeClient()` (it reads its settings from env), then call `client.system_one(state, questions)`.
- **Async:** use `async with AsyncTypeSafeClient() as client:` and `await client.system_one(state, questions)`.
- The quickstart on python.md uses a **dict** state with one `document` key holding a support-ticket string. The usage page uses a **plain string** state. Both are valid because `state` is `JSONContent`.
- The questions dict maps a name to a question object:
  - `billing` is a `Noul` with instructions only.
  - `tone` is a `Choice`. Its criteria dict is keyed by label, e.g. calm/frustrated/angry, and the values are descriptions or `None`.
  - `urgency` is a `Score`. Its criteria are an ordered **list**, e.g. can wait / this week / today, or low / medium / high.
- Results are read as `result.nouls["billing"].noul` (a float), `result.choices["tone"].choice` (a str) and `result.scores["urgency"].score` (a float).

Source: https://docs.typesafe.ai/sdk/python.md , https://docs.typesafe.ai/sdk/python/usage.md

## 3. Clients: `TypeSafeClient` (sync) and `AsyncTypeSafeClient`
The constructor takes keyword-only arguments, and both clients have the same shape:
- `api_key: str | None = None` (env `TYPESAFE_API_KEY`, required overall)
- `model: str | None = None` (env `TYPESAFE_DEFAULT_MODEL`, default `jev-latest`)
- `retry: RetryPolicy | None = None` (pass `RetryPolicy(max_retries=0)` to disable retries)
- `timeout: float | httpx2.Timeout | None = None`. If an `http_client` is supplied, this inherits `http_client.timeout`. Otherwise it uses the SDK default, which is `DEFAULT_TIMEOUT` = 10.0 s **per HTTP operation**.
- `headers: Mapping[str, str] | None = None`, extra headers added to every request.
- `transport`: `httpx2.BaseTransport` for sync, `httpx2.AsyncBaseTransport` for async. Closing the client also closes the transport.
- `http_client`: `httpx2.Client` for sync, `httpx2.AsyncClient` for async. It is **mutually exclusive** with `transport`; passing both raises `ValueError`. `aclose()` also closes a user-supplied client.
- `base_url: str | None = None` (env `TYPESAFE_BASE_URL`, default `https://api.typesafe.ai`)

Constructor errors: `TypeSafeError` for a bad API key or timeout, and `ValueError` when both `transport` and `http_client` are passed.

Members:
- `models` is a cached property. It returns a `Models` accessor (sync) or `AsyncModels` accessor (async).
- `system_one(state, questions, *, model=None, retry=None, timeout=None, extra_headers=None, extra_body=None, response_model=None)` returns `SystemOneResponse | ResponseT`. It is `async` on the async client.
  - `state: JSONContent` is text, a JSON object or a JSON array. It must not be `None`, but values inside an object may be `None`.
  - `questions: Mapping[str, Question]` must be **non-empty**.
  - `model` overrides the model for this call. `None` means the client default.
  - `retry` overrides the retry policy for this call, and `timeout` overrides the timeout for this call (in seconds).
  - `extra_headers: Mapping[str, str]`. Auth, SDK-ID and `Accept` headers stay protected and cannot be overridden.
  - `extra_body: Mapping[str, JSONValue | None]` adds top-level request-body fields. Merging is a shallow last-write-wins: a key named `state`, `model` or `questions` **overrides** the SDK value, and object values are replaced, not deep-merged. The example passes an unsupported field as `{"beam_width": 4}`.
  - `response_model: type[ResponseT]` is an optional pydantic `BaseModel` type that describes the JSON response body.
  - Errors:
    - `TypeSafeError` for empty questions or empty criteria (client-side validation)
    - `TypeSafeAPIError` for a non-2xx response
    - `TypeSafeAPIConnectionError` for connection failures and timeouts
    - `TypeSafeAPIResponseValidationError` for a 2xx response with bad or missing data
- Closing: `close()` on sync or `await aclose()` on async. Sync supports `with`, async supports `async with`.
- `models.list(*, retry=None, timeout=None, extra_headers=None)` returns `ListModelsResponse`. It can raise `TypeSafeAPIError` or `TypeSafeAPIConnectionError`.

Not stated:
- HTTP method and endpoint paths (for example what `system_one` or `models.list` POST or GET to)
- The exact request JSON field names beyond `state`, `model` and `questions`
- Thread safety, connection pooling, HTTP/2 and event-loop constraints

Source: https://docs.typesafe.ai/sdk/python/api/clients/sync.md , https://docs.typesafe.ai/sdk/python/api/clients/async.md

## 4. Question types (`typesafe_sdk.Noul`, `Choice`, `Score`, all pydantic models)
- **`Noul`** is a yes/no or true/false probability question.
  - `type: Literal['noul']` is set by default.
  - `instructions: JSONContent | None = None`
  - `criteria: NoulCriteria | None = None`. `NoulCriteria` is a TypedDict with keys `true` and `false`, each `JSONContent | None`, describing the yes and no outcomes. Whether those keys are optional (`total=False`) is not stated.
- **`Choice`** picks one label.
  - `type: Literal['choice']`
  - `instructions: JSONContent | None = None`
  - `criteria: Mapping[str, JSONContent | None]` is **required** and maps a label to its description or `None`. Empty criteria are rejected client-side.
- **`Score`** is an ordinal rubric.
  - `type: Literal['score']`
  - `instructions: JSONContent | None = None`
  - `criteria: Sequence[JSONContent]` is **required** and must be non-empty. It is ordered, with one description per level starting at score 0. Since v0.6.0 this is a sequence; it used to be a dict keyed by int.
- **Dict forms** are TypedDicts named `NoulModel`, `ChoiceModel` and `ScoreModel`, discriminated by the `"type"` key. In them `instructions` is `NotRequired` and `criteria` follows the same rules as above.
- Type aliases:
  - `Question` = `Noul | Choice | Score | QuestionModel`
  - `Questions` = `Mapping[str, Question]`
  - `QuestionModel` = `NoulModel | ChoiceModel | ScoreModel`
- Raw dicts skip SDK type checking. The usage page passes an undocumented `weight: 2` key this way as a forward-compatibility example.
- Stated limits: none. The docs give no maximum number of questions or criteria and no length limits. Pydantic config for the question models is not stated.
- Concept links: /primitives/noul, /primitives/choice, /primitives/score.

Source: https://docs.typesafe.ai/sdk/python/api/types/questions.md , https://docs.typesafe.ai/sdk/python/usage.md

## 5. Common types
- `JSONValue` is a TypeAliasType covering `str | int | float | bool | Sequence[JSONValue | None] | Mapping[str, JSONValue | None]`. It can be nested and can contain `None`.
- `JSONContent` is `str | Mapping[str, JSONValue | None] | Sequence[JSONValue | None]`.
- No other common types appear on the page.

Source: https://docs.typesafe.ai/sdk/python/api/types/common.md

## 6. Response types
All response models use pydantic `ConfigDict(extra="ignore", frozen=True, strict=True)`. Unknown fields are **silently ignored**, objects are immutable, and validation is strict. One summary line said they "reject" extra fields, but the config is `ignore`.

**`SystemOneResponse`**
- Fields:
  - `model: str`, the model that answered
  - `usage: Usage`
  - `answers: dict[str, Answer]`
- Properties:
  - `request_id` is a cached str taken from the `x-typesafe-request-id` response header.
  - `raw_http_response` returns an `httpx2.Response`.
  - `nouls: dict[str, NoulAnswer]`, `choices: dict[str, ChoiceAnswer]` and `scores: dict[str, ScoreAnswer]` are cached filters over `answers`.

**`Usage`**
- `input_tokens: int | None = None`
- `output_tokens: int | None = None`

**`Answer`** is `Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]`.
- **`NoulAnswer`**: `type`, plus `noul: float`, the probability of yes or true in the range 0 to 1. Values near 0.5 mean uncertain.
- **`ChoiceAnswer`**: `type`, plus:
  - `choice: str`, the label with the highest probability
  - `confidence: float` from 0 to 1, where low means uncertain
  - `probabilities: dict[str, float]`, the probability of each label
- **`ScoreAnswer`**: `type`, plus:
  - `score: float`, the expected value (probability-weighted average of the levels), so it **can fall between integers**
  - `confidence: float` from 0 to 1
  - `legend: dict[int, str | dict | list]`, the level descriptions
  - `probabilities: dict[int, float]`

**Unknown answer kinds** are logged as a warning and skipped, so they never appear in `answers`. To see them, read `result.raw_http_response.json()["answers"]`.

**`ListModelsResponse`**
- `models: tuple[ModelMetadata, ...]`, plus the same `request_id` and `raw_http_response` properties.
- `ModelMetadata` has `name: str` (a name or alias accepted as `model`), `description: str` and `release_date: str` in YYYY-MM-DD format.

**Typed responses (v0.7.0+)**
- **Option (a):** subclass `SystemOneResponse` and add a field such as `billing: NoulAnswer`, then pass `response_model=ThatClass`. You read `result.billing.noul`, which is the same object as `result.nouls["billing"]`.
- **Option (b):** use a plain `BaseModel` that mirrors the body, e.g. an `answers` field whose nested model has `billing: NoulAnswer`. You read `result.answers.billing.noul`.

Source: https://docs.typesafe.ai/sdk/python/api/types/responses.md , https://docs.typesafe.ai/sdk/python/usage.md

## 7. RetryPolicy (a dataclass; frozen/slots not stated)
Defaults:
- `max_retries: int = 2` counts retries after the first attempt. 0 disables retries.
- `backoff_initial: float = 0.5` seconds. The delay doubles on each attempt up to `backoff_max`. 0 disables backoff.
- `backoff_max: float = 5.0` seconds. 0 disables backoff.
- `backoff_jitter: float = 0.25` must be between 0 and 1. A random fraction of each delay up to this value is subtracted.
- `http_statuses: set[int]` defaults to {408, 429, *range(500, 600)}.
- `respect_retry_after: bool = True` honors the `Retry-After` and `retry-after-ms` headers.
- `api_connection_error: bool = True` retries `TypeSafeAPIConnectionError`.
- `api_timeout_error: bool = True` retries `TypeSafeAPITimeoutError`.
- `exceptions: set[type[BaseException]] = set()` lists extra exception types that trigger a retry.
- `predicate: Callable[[BaseException], bool] | None = None`. A True result triggers a retry.
- `timeout: float | None = 30.0` is the **total budget per SDK call**. It covers the first attempt, all retries and all delays. The SDK stops before a retry whose delay would reach or pass the remaining budget.

This gives two timeout layers: the per-HTTP-operation client or call timeout (default 10 s) and the total `RetryPolicy.timeout` budget (default 30 s).

The usage example is `RetryPolicy(max_retries=3, backoff_max=0.2, timeout=1.0)`. It can be passed client-wide as `retry=` on the constructor or per call as `retry=` on `system_one`.

Since v0.6.0, invalid `RetryPolicy` values are "handled". Which exception is raised is not stated.

Not stated:
- Idempotency keys, and whether a POST retry is idempotent
- Whether Retry-After is capped by `backoff_max`

Source: https://docs.typesafe.ai/sdk/python/api/retries.md , https://docs.typesafe.ai/sdk/python/usage.md

## 8. Exceptions
Hierarchy:
- `TypeSafeError(Exception)`
  - `TypeSafeAPIError`
    - Status-specific subclasses:
      - `TypeSafeBadRequestError` for 400
      - `TypeSafeAuthenticationError` for 401
      - `TypeSafePermissionDeniedError` for 403
      - `TypeSafeNotFoundError` for 404
      - `TypeSafeUnprocessableEntityError` for 422
      - `TypeSafeRateLimitError` for 429
      - `TypeSafeInternalServerError` for 5xx
    - `TypeSafeAPIResponseValidationError`
  - `TypeSafeAPIConnectionError`, which also subclasses `ConnectionError`
    - `TypeSafeAPITimeoutError`, which also subclasses `TimeoutError`

Attributes on `TypeSafeAPIError`:
- `status: int`
- `body: dict | str | None`, the JSON error body or plain text
- `headers: dict`
- `endpoint: str`, the method and URL with credentials, query and fragment removed
- `request_id: str | None`, from `x-typesafe-request-id`

Subclass attributes:
- `TypeSafeRateLimitError.retry_after_ms: int | None`
- `TypeSafeAPITimeoutError.timeout: float | httpx2.Timeout`
- `TypeSafeAPIResponseValidationError.field_path: str`, a dotted path such as `answers.tone.confidence`

Since v0.6.0, exceptions and responses can be pickled.

Not stated: which class is raised for other 4xx codes such as 409 (presumably the base `TypeSafeAPIError`, but this is unconfirmed), and constructor signatures.

Source: https://docs.typesafe.ai/sdk/python/api/exceptions.md

## 9. Constants (`typesafe_sdk.constants`)
- `API_KEY_ENV` = 'TYPESAFE_API_KEY'
- `BASE_URL_ENV` = 'TYPESAFE_BASE_URL'
- `DEFAULT_MODEL_ENV` = 'TYPESAFE_DEFAULT_MODEL'
- `LOG_LEVEL_ENV` = 'TYPESAFE_LOG_LEVEL'
- `DEFAULT_BASE_URL` = 'https://api.typesafe.ai'
- `DEFAULT_MODEL` = 'jev-latest'
- `DEFAULT_TIMEOUT` = 10.0, in seconds per HTTP operation

Source: https://docs.typesafe.ai/sdk/python/api/constants.md

## 10. Logging, models, gateways
- **Logging**
  - The logger name is `typesafe_sdk`. `TYPESAFE_LOG_LEVEL` accepts debug, info, warning, error or off, and must be set before import.
  - `info` logs one summary line per request. `debug` adds headers and bodies.
  - The SDK redacts Authorization, API keys, cookies and any header whose name contains token or secret. **Request and response bodies are NOT redacted**, so debug logs will contain the state and questions.
- **Models:** call `client.models.list()` to see the available models. Examples use `model="jev"`; the default is `jev-latest`.
- **Gateways:** any base URL must follow the TypeSafe OpenAPI spec.
  - OpenRouter: base_url `https://openrouter.ai/api`, key from `OPENROUTER_API_KEY`, model `~typesafe/jev-latest`.
  - Vercel AI Gateway: base_url `https://ai-gateway.vercel.sh/typesafe`, key from `AI_GATEWAY_API_KEY`, model `typesafe-ai/jev`.

Source: https://docs.typesafe.ai/sdk/python/usage.md

## 11. Changelog
- **v0.5.7** (2026-09-14): first public release.
- **v0.6.0** (2026-09-15):
  - BREAKING: `Score.criteria` is now an ordered sequence instead of a dict keyed by int.
  - Better `Mapping`/`Sequence` annotations.
  - Error messages now include HTTP details.
  - Invalid RetryPolicy values are handled.
  - Exceptions and responses can be pickled.
- **v0.7.0** (2026-09-18):
  - BREAKING: ser/de moved from `msgspec` to `pydantic`.
  - `str` subclasses are now serialized as strings instead of lists of characters.
  - New `response_model` argument.
- **v0.7.1** (2026-09-21):
  - The API key is validated early and kept out of logged exceptions.
  - AI-gateway examples were added.

Source: https://docs.typesafe.ai/sdk/python/changelog.md

## 12. API index page
The index only links to the pages above: sync and async clients, common, questions and responses types, retries, exceptions and constants. It points to https://docs.typesafe.ai/llms.txt as the full docs index.

Source: https://docs.typesafe.ai/sdk/python/api.md

## Caveats
- **Browser automation:** the SDK does not drive a browser and has no CDP, Playwright, screenshot or image support in these pages. The only input is JSON or text `state`. The docs do not say whether images are supported.
- **Pricing, rate limits, latency:** none are stated in this group.
