# Coding Guidelines

> [!NOTE]
> These are the **general** engineering guidelines for this repository: they
> apply to every application and every language. Domain- and app-specific rules
> live in separate documents — see the resolution order below. Anything not
> covered by a more specific document is governed here.

## Document resolution order

Read these in order. A more specific document augments a more general one; it
does not replace it. Where the two differ, the more specific document takes
precedence.

| Order | Document | Covers |
|---|---|---|
| 1 | `CODING_GUIDELINES.md` | General engineering rules, all languages |
| 2 | `FRONTEND.md` | Frontend/UI: React, styling, motion, accessibility |
| 3 | `<app>/AGENTS.md` | App layout, commands, app-specific conventions |

For `CODING_GUIDELINES.md` and `FRONTEND.md`, **read the root copy, then the
copy in the application directory you are working in, where it has one.** An
application-level copy augments the root document; it does not replace it.
Where the two differ, the application-level copy takes precedence.

Contribution process, PR expectations, and review policy live in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 1. Principles

### 1.1 Simplicity first

* Write the minimum code that solves the problem. Nothing speculative.
* Do not add features, parameters, options, or configuration that were not asked
  for. Do not build abstractions for single-use code.
* Do not handle impossible cases. Handle the ones that can actually occur.
* Prefer explicit, readable code over dense one-liners, clever regexes, and
  metaprogramming. Code is read and debugged far more often than written.
* Ask of every change: *would a senior engineer call this overcomplicated?* If a
  50-line implementation works, do not write 200.

### 1.2 Surgical changes

* Every changed line must trace directly to the stated goal of the change.
* Do not "improve" adjacent code, comments, or formatting that is unrelated to
  your change; unrelated churn expands the review surface and hides the real
  diff.
* Match the existing style and patterns of the file you are editing, even where
  you would have chosen differently.
* Clean up orphans **you** created (unused imports, variables, functions). Leave
  pre-existing dead code alone — mention it instead.
* Remove debugging logs, commented-out code, and scratch files before
  submitting.

### 1.3 Think before coding

* State assumptions explicitly. If a requirement has more than one plausible
  reading, raise it instead of silently picking one.
* If a simpler approach exists than the one requested, say so.
* If something in the codebase is unclear, stop and ask rather than guessing.

### 1.4 Goal-driven execution

Turn tasks into verifiable goals before writing code:

* "Add validation" → write tests for the invalid inputs, then make them pass.
* "Fix the bug" → write a reproducing test, then make it pass.
* "Refactor X" → tests pass before and after, unchanged.

### 1.5 Architecture and dependencies

* Evaluate the approach before the diff: is this the right strategy, does it
  work *with* the framework and existing patterns rather than against them, and
  is there already a pattern in this codebase that solves it?
* Justify every new third-party dependency: can the standard library or an
  existing dependency do it? Is the package maintained, appropriately sized, and
  free of known vulnerabilities? Do not add a large dependency for a trivial
  utility.

---

## 2. Language style guides and toolchains

All languages follow the relevant
[Google Style Guide](https://google.github.io/styleguide/). The formatter and
linter configured in the application are authoritative for mechanical formatting
— never fight them, and never relax a rule globally to silence a single site.

Mechanical formatting — line width, indentation, quote style — is owned by the
application's formatter and is not restated here.

| Language | Style guide | Tooling |
|---|---|---|
| TypeScript / JavaScript | [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html) | Biome, ESLint, or `tsc` as configured per app |
| HTML / CSS / SCSS | [Google HTML/CSS Style Guide](https://google.github.io/styleguide/htmlcssguide.html) | Stylelint / Biome as configured per app |
| Python | [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) | `ruff` (format + check) and `mypy` (strict) for new code; existing apps keep their configured toolchain |
| Go | [Google Go Style Guide](https://google.github.io/styleguide/go/) | `gofmt`, `go vet`, `golangci-lint` |
| Java | [Google Java Style Guide](https://google.github.io/styleguide/javaguide.html) | `google-java-format` |
| Shell | [Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html) | `shellcheck` |
| Markdown / prose | [Google Developer Documentation Style Guide](https://developers.google.com/style/) | — |

Suppress a check only for the specific line that needs it, with a comment
explaining why (e.g. `# pylint: disable=line-too-long`,
`// biome-ignore lint/suspicious/noExplicitAny: <reason>`).

---

## 3. Structure and organization

* **Respect the existing hierarchy.** New files go where comparable files
  already live. Do not invent a one-off directory without precedent.
* **Name directories and files for their domain**, not their genericity.
  `misc/`, `common/`, `helpers/`, and `utils/` dumping grounds without clear
  ownership are rejected.
* **Single responsibility per file.** A file that mixes transport routing,
  business logic, external clients, and helpers should be decomposed.
* **Tight modules, concise functions.** A function does exactly one thing. A
  module groups one coherent concern. This maximizes reuse, simplifies unit
  testing, and lowers cognitive load.
* **Flat by default; no anticipatory nesting.** Promote a file to a folder only
  when it actually gains a child used solely by it. Do not create folders for
  files that do not exist yet.
* **Narrowest scope that owns it.** Code used by exactly one feature lives with
  that feature, not in a shared directory.
* **Colocate tests** with the code they test (`feature.test.ts` next to
  `feature.ts`, `foo_test.py` next to `foo.py`). Do not dump tests into a
  distant flat catch-all directory.

### 3.1 File naming

* `snake_case` for source files by default (`chat_pipeline.py`,
  `use_branding.ts`, `card_chart.tsx`).
* `dash-case` only where a framework requires it — e.g. Next.js App Router
  segments under `apps/web/src/app`.
* `PascalCase` for component/class identifiers (`CardChart`), regardless of the
  file name.
* **Category first.** Composed names lead with *what the thing is*, then what
  makes it specific: `card_chart` (not `chart_card`), `button_close`,
  `icon_arrow_right`. This groups related files in sorted listings, makes
  fuzzy-find match by category, and keeps imports visually parallel. Applies to
  files, folders, identifiers, and CSS classes.
* No relative parent imports (`../`). Use the project's path alias (`~/`, `@/`)
  so files can move without rewriting import paths.

---

## 4. Naming

* **Self-documenting over terse.** `source` not `s`, `index` not `i`, `message`
  not `m`, `calculateTotal` not `calcTotal`. Single letters are acceptable only
  in a trivial one-line loop or lambda.
* **Prefer the long, explicit name** over an acronym:
  `DataCommonsComponentTagName` beats `DCTag`. Long names document themselves
  and work better with autocomplete.
* **Verb-led function names** — `getComponentAttributes`, `resolvePlaceDcid`;
  not a bare noun.
* **Boolean prefixes** — `is`, `has`, `should` (`isLoading`, `hasFooter`).
* **Name reusable assets by what they represent, not by their current
  call-site.** An icon that draws a pencil is `icon_pencil`, not `icon_export` —
  so it still reads correctly at the next call-site.
* **Follow the ecosystem's casing.** `camelCase` properties in TypeScript
  (`brandConfigUrl`, not `brand_config_url`); `snake_case` in Python.

---

## 5. No magic values

* Extract raw numbers, thresholds, limits, and durations into named constants at
  module scope: `MAX_PREVIEW_LENGTH = 500`, `MS_PER_MINUTE = 60_000`.
* Prefer idiomatic empty values (`''`, `null`, `None`) over invented sentinels
  (`'none'`, `-1`) that force redundant checks downstream.
* Do not hardcode environment-, tenant-, or event-specific values
  (`"AISummit2026"`, a single instance's bucket name) in shared code. Take them
  from configuration.

---

## 6. TypeScript

* **`interface` for object shapes**; a component's props are
  `ComponentNameProps`. `type` is for unions, tuples, mapped types, and function
  types.
* **Named exports only.** `export default` is permitted only where a framework
  requires it (Next.js files under `src/app/**`, `*.config.*`).
* **`import type` / `export type`** for type-only imports and re-exports.
* **No `any`.** Use `unknown` and narrow. If truly unavoidable, suppress the
  single line with a comment explaining why.
* `===` / `!==` only. `const` by default. Braced control statements.
* Prefer arrow functions. Mark a function `async` only when it `await`s.
* Avoid nested ternaries and complex inline conditions in JSX or arguments —
  lift them into a named constant, helper, or lookup object.
* JSDoc every exported function, hook, interface, and constant whose intent is
  not obvious from the signature. Explain *why*, not just *what*.

Vitest-specific conventions:

* Stub environment variables with `vi.stubEnv('KEY', 'value')` and restore with
  `vi.unstubAllEnvs()`. Never assign `process.env.KEY = undefined` — Node
  coerces it to the string `"undefined"`, leaving the variable truthy.
* Stub globals with `vi.spyOn(globalThis, 'fetch')` or `vi.stubGlobal(...)`
  paired with `vi.unstubAllGlobals()`. Direct assignment to `globalThis` is not
  undone by `vi.restoreAllMocks()` and leaks into other test files.

---

## 7. Python

* Follow the Google Python Style Guide; 4-space indent, `snake_case` functions
  and modules, `PascalCase` classes.
* Type-hint public function signatures. Write an optional parameter as
  `X | None`, never as a bare `X` with a `None` default — an implicit optional
  misstates the signature, and `ruff` rejects it.
* **New and rewritten Python type-checks under `mypy --strict`, and CI fails on
  any error.** A new module is annotated as it is written, and is never added
  to the exemption list.
* Modules that predate the standard are exempted individually in the app's
  `pyproject.toml`, under `[[tool.mypy.overrides]]` with `ignore_errors`. Each
  entry names the change that rewrites or deletes the module it covers. An
  exemption is retired by deleting that module, never by annotating code that
  is scheduled for replacement. **The list only shrinks**, and it should reach
  the standard small set — third-party stubs and nothing else.
* Module-level docstring describing the file's responsibility; docstrings on
  public functions covering arguments, return value, and raised exceptions.
* Use the `logging` module, never `print`, for anything that runs in a server or
  pipeline. Reserve `print` for CLI output intended for the user.
* Catch specific exceptions. A bare `except Exception` is acceptable only at a
  process or request boundary, and must log with context and re-raise or return
  a well-defined failure.
* Declare dependencies in the app's single canonical manifest
  (`requirements.txt` / `pyproject.toml`); pin versions.

---

## 8. Error handling and logging

* **Fail fast and loudly.** Never swallow an error silently. If a failure is
  deliberately ignored, a comment must say why.
* **Add context when propagating.** An error should tell the reader which
  operation failed and on which input — not just that something failed.
* **Distinguish expected from exceptional.** Missing data for a query is an
  expected outcome to be surfaced in the UI; a malformed API response is an
  error to be logged.
* **Log at the right level**: `debug` for tracing, `info` for lifecycle events,
  `warning` for degraded-but-handled conditions, `error` for failures that need
  attention.
* **Never log secrets, credentials, tokens, or user PII**, and never echo a full
  API key or authorization header, even truncated.

---

## 9. Lifecycle, concurrency, and resilience

* **Guard re-entrancy.** Think through rapid double-clicks, concurrent requests,
  and overlapping invocations. Where simultaneous execution would corrupt shared
  state, add an in-progress guard and return early.
* **Check liveness before acting on a resource.** For DOM work, verify the node
  is still connected (`if (!target?.isConnected) return;`) before mutating it;
  components unmount while async work is in flight.
* **Guarantee cleanup.** Side-effects, temporary DOM tagging, subscriptions, and
  allocated resources are released in `finally` (or the language's equivalent)
  so cleanup runs even on the exception path.
* **Abort multi-stage pipelines on failure.** When an early phase fails, halt
  explicitly instead of running downstream stages against half-built state.
* **No arbitrary sleeps.** Replace `sleep(5)` with a bounded polling loop, an
  event, or a documented timeout.
* **Cancel superseded work.** Long-running fetches and streams that a newer user
  action has invalidated should be aborted, not left to race.

---

## 10. Performance and resource safety

* Watch algorithmic complexity: avoid accidental O(n²) nested scans; use a
  `Set`/`Map`/`dict` for repeated membership or key lookups.
* Stream large payloads and files instead of buffering them entirely in memory.
* Close or scope every file, connection, subscription, and subprocess (context
  managers, `defer`, `try/finally`).
* Do the work where it belongs — see §12.3 for the server/client boundary.

---

## 11. Security, secrets, and input handling

* **Secrets never live in code, config files, or committed `.env` files.** Use
  Secret Manager or the runtime environment. Provide a `.env.example` with
  placeholder values instead.
* **Secrets never reach the client bundle.** API keys stay server-side; the
  browser talks to your own endpoint, which talks to the upstream service.
* **Least privilege.** CI workflows request the minimum scopes
  (`permissions: contents: read` unless more is genuinely needed); service
  accounts get the narrowest role that works.
* **Treat all external input as untrusted** — URL hash and query parameters,
  request bodies, model output, and third-party API responses. Validate and
  sanitize before using it in a query, a shell command, navigation, or rendered
  HTML.
* Never interpolate unescaped input into DOM-rendering paths (XSS) or redirect
  targets (open redirect).
* Pin GitHub Actions to a commit SHA with the version in a trailing comment.

---

## 12. Data Commons pipeline conventions

Applications in this repository share the same shape: **prompt → model → MCP
tools → app server → client store → UI.** Most quality problems come from doing
work at the wrong layer.

### 12.1 Field origins and prompt contracts

For every field flowing through the pipeline (`placeDcid`, `childPlaceType`,
`resolvedPlaceDcid`, …), know where it originates: model output, MCP tool
response, REST response, or client parameter. If the model produces it, the
prompt must define the field, its type, and valid examples. An undocumented
field in a prompt is an unenforced contract.

### 12.2 Push work upstream

Before adding string matching, case normalization, or lookup tables in the app
server to repair a tool response, ask whether the MCP server can return that
information as structured metadata, or the prompt can instruct the model to emit
canonical values directly. Defensive fallbacks are sometimes necessary for
reliability — when they are, note the upstream fix they stand in for.

### 12.3 Server versus client

* **Shape payloads server-side.** Prune and reshape heavy Data Commons responses
  before sending them over the wire; do not dump raw API responses into the
  client.
* **Aggregate server-side.** Joins, filtering, ranking, and time-series
  restructuring belong on the server.
* **Keep the client light.** Client work is limited to responsive UI
  transformations — selectors, viewport projection, formatting — so the main
  thread stays unblocked.

### 12.4 Data integrity

* **Ordering is not guaranteed.** Sort observations ascending by date before
  charting or computing deltas.
* **Validate before arithmetic.** Filter out nullish values and malformed dates
  (`typeof obs?.date === 'string'`) before sorting or math.
* **Preserve place ↔ variable binding through fallbacks.** When the pipeline
  falls back to a parent place or `Earth`, the fallback variable must be queried
  against the fallback place — querying the original place with the fallback
  variable produces false "no data".
* **Respect result limits.** Queries returning hundreds or thousands of child
  entities need pagination, ranking, or top-N handling.
* **Make cache and store keys collision-proof.** Distinguish a parent query
  (`africa`) from a child query (`africa:Country`) and from a multi-entity
  comparison (`KEN+UGA`), and invalidate accordingly.

---

## 13. Testing

* **Every new feature, component, hook, endpoint, or utility ships with tests.**
  Modifying legacy code means updating or adding its tests.
* **Every bug fix ships with a test that fails before the fix.**
* **Colocate and name conventionally**: `*.test.ts` / `*.test.tsx` for
  TypeScript, `*_test.py` for Python, `*_test.go` for Go.
* **Assert behavior, not implementation.** A test that only proves a mock was
  called, or restates the implementation, has no value. Tests should survive an
  internal refactor that preserves behavior.
* **Cover the failure modes**: null/undefined inputs, empty collections,
  malformed dates, boundary values, network and timeout errors, and permission
  failures — not just the happy path.
* **Be minimal.** The smallest set of cases that establishes correctness; target
  complex and high-risk paths rather than padding coverage.
* **Be deterministic.** No reliance on wall-clock sleeps, real network calls, or
  test execution order.
* **Golden/snapshot files are regenerated by a checked-in script**, never
  hand-edited, and every diff is reviewed as a deliberate change.
* **Document each case with structured comments**, adapted to the language:

  ```ts
  // Test: Multi-page response.
  // Situation: The data source returns 3 pages linked by nextToken.
  // Expectation: The helper fetches all 3 pages and merges the nodes.
  ```

---

## 14. Documentation and comments

* **File-overview header** on any file carrying a complex workflow or
  orchestration, stating its scope and architectural responsibility.
* **Document exported symbols** — inputs, outputs, and failure cases — so
  callers do not have to read the body. Explain *why* a non-obvious approach was
  taken.
* Comments explain intent and constraints. Do not narrate what the code already
  says.
* **Wrap Markdown and documentation at 80 characters.** Exemptions, because the
  format forbids a line break:
  * **Table rows.** A pipe-table row cannot be split across lines. Keep cells
    short — a few words — and push explanation into prose below the table. If a
    cell needs a sentence, the content wants a list or a subsection, not a
    table.
  * **Unbreakable tokens** — a URL, an import path, or an inline code span that
    is itself longer than the limit. Wrap around it; do not mangle it.
  * **Fenced code blocks**, which reproduce real code or terminal output. Keep
    the code itself within 80 columns where the language allows.
* Follow the Google Developer Documentation Style Guide for prose.
* In multi-line shell examples, ensure no trailing whitespace after a `\`
  continuation — it breaks copy-paste.
* **Every new source file carries the Apache 2.0 license header** in the comment
  syntax of its language, with the current year:

  ```python
  # Copyright <current year> Google LLC
  #
  # Licensed under the Apache License, Version 2.0 (the "License");
  # you may not use this file except in compliance with the License.
  # You may obtain a copy of the License at
  #
  #      http://www.apache.org/licenses/LICENSE-2.0
  #
  # Unless required by applicable law or agreed to in writing, software
  # distributed under the License is distributed on an "AS IS" BASIS,
  # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
  # implied. See the License for the specific language governing
  # permissions and limitations under the License.
  ```

---

## 15. Shell scripts and CLIs

* **Path independence.** Resolve paths relative to the script, not the caller's
  working directory:
  `DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"`.
* `set -euo pipefail` in every Bash script.
* Provide `--help` output, and iterate over all arguments (`"$@"`) rather than
  inspecting only `$1`.
* Validate required inputs and fail with a clear message, not a stack trace.

---

## 16. Verification before submitting

Run the application's full verification suite locally before opening or updating
a PR. Do not guess commands — each app documents its own in `<app>/AGENTS.md`:

| App | Lint / types | Tests | Build |
|---|---|---|---|
| `dataweaver` | `pnpm lint` | `pnpm test` | `pnpm build` |
| `narratives`, `ui/` | `npm run lint` | `npm run test` | `npm run build` |
| `narratives`, `agent/` | `uv run ruff check .`, `uv run mypy` | `uv run pytest` | — |

`narratives` has two toolchains and both gate the merge; running only the npm
commands leaves the Python side unchecked. The agent also runs
`uv run ruff format --check .`, which has no column above because it is a
formatter rather than a linter.

For UI changes, also run the production build and verify the change manually in
the browser. Every app must be wired into the CI orchestrator so that
`CI Final Status` gates the merge — see
[`CONTINUOUS_INTEGRATION.md`](CONTINUOUS_INTEGRATION.md).

---

## 17. Keeping these documents current

* A change that introduces a new standard, architectural pattern, command, or
  convention must update the relevant document **in the same PR**.
* Put each rule in exactly one place: general rules here, UI rules in
  `FRONTEND.md`, app-specific rules in `<app>/AGENTS.md`. Cross-reference
  instead of duplicating.
* Reviewers — human or agent — flag changes that violate these guidelines, and
  flag guidelines that the codebase has outgrown.
