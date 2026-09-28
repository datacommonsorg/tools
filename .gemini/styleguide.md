# Gemini Code Assist Review Style Guide

This style guide defines the automated code review checklist for pull requests
in `datacommonsorg/tools`. Focus on correctness, architecture, security, and
code health. Do not comment on mechanical formatting enforced by linters or
formatters.

---

## 1. Comment Protocol & Severity Tags

Prefix every review comment with an appropriate severity tag:

* `[BLOCKER]` — Correctness bugs, memory/resource leaks, unhandled failure
  paths, missing cleanup, security or secret exposure, broken typing (`any`),
  and regressions.
* `[WARNING]` — Performance bottlenecks under load, excessive complexity, or
  risky architectural patterns.
* `[SUGGESTION]` — Readability improvements, naming, constant extraction, or
  simplification. Non-blocking.
* `[FOLLOWUP]` — Pre-existing technical debt adjacent to the change; acceptable
  now, should be tracked separately.
* `[NIT]` — Typos, prose clarity, or trivial consistency.

### Tone & Structure
* **Name the flaw** in the first clause.
* **Explain the mechanism**: cite line numbers and walk the execution path.
* **Prescribe the fix**: provide concrete replacement snippets or suggestions.
* Where relevant, cite the governing repository document
  (`CODING_GUIDELINES.md`, `FRONTEND.md`, or `<app>/AGENTS.md`).

---

## 2. General Principles

* **Simplicity first**: Write the minimum code that solves the problem. Flag
  speculative features, unused parameters, or abstractions for single-use code.
* **Surgical diffs**: Every changed line must trace directly to the PR's stated
  goal. Flag unrelated reformatting, drive-by refactoring, or touched adjacent
  code.
* **No magic values**: Extract raw numbers, thresholds, and durations into
  named constants at module scope.
* **Naming**:
  * Self-documenting over terse (`source` not `s`, `index` not `i`).
  * Verb-led function names (`getComponentAttributes`, `resolvePlaceDcid`).
  * Boolean prefixes (`isLoading`, `hasFooter`, `shouldRetry`).
  * Composed names lead with category first: `card_chart` (not `chart_card`),
    `button_close`, `icon_arrow_right`.

---

## 3. Structure & File Conventions

* **Source file naming**: `snake_case` by default (`chat_pipeline.py`,
  `card_chart.tsx`). Next.js App Router folders use `dash-case`.
* **Classes & Components**: `PascalCase` (`CardChart`), regardless of file name.
* **Imports**: No relative parent imports (`../`). Use project path aliases
  (`~/`, `@/`).
* **License headers**: Every new source file must carry the standard Apache 2.0
  license header.
* **Markdown wrapping**: Wrap prose in Markdown files at 80 characters (except
  table rows, unbreakable URLs, and code blocks).

---

## 4. TypeScript & JavaScript

* **Object shapes**: Use `interface` for object shapes and props
  (`ComponentNameProps`). Use `type` for unions, tuples, and mapped types.
* **Exports**: Named exports only. `export default` is allowed only where a
  framework requires it (Next.js route files, config files).
* **Type imports**: Use `import type` and `export type` for type-only symbols.
* **Strict typing**: No `any`. Use `unknown` and narrow with type guards.
* **Equality & Control**: `===` and `!==` only. `const` by default. Mark a
  function `async` only when it contains an `await`.
* **Tests**: Colocate tests (`foo.test.ts` next to `foo.ts`). Never assign
  `process.env.KEY = undefined`; use `vi.stubEnv` and `vi.unstubAllEnvs`.

---

## 5. Python

* **Style & Types**: Follow Google Python Style Guide. 4-space indent,
  `snake_case` functions/modules. All new code must pass `mypy --strict`.
* **Signatures**: Explicit type hints on public functions. Optional parameters
  must be typed as `X | None`, never bare `X = None`.
* **Logging**: Use the `logging` module, never `print`, for server or pipeline
  code.
* **Error handling**: Catch specific exceptions. Never swallow exceptions
  silently. Bare `except Exception` is permitted only at request boundaries and
  must log context and re-raise or return a structured error.

---

## 6. Concurrency, Lifecycle & Resilience

* **Re-entrancy**: Guard rapid user interactions or overlapping async actions
  with in-progress flags.
* **DOM Liveness**: Check `if (!target?.isConnected) return;` before mutating
  DOM nodes after asynchronous pauses.
* **Guaranteed cleanup**: Subscriptions, event listeners, intervals, and
  temporary state must be cleaned up in `finally` blocks or `useEffect`
  cleanup functions.
* **No arbitrary sleeps**: Replace `sleep(5)` with bounded polling or events.
* **Resource cleanup**: Scope every file, connection, and stream using context
  managers (`with`) or `try/finally`.

---

## 7. Security & Secrets

* **No secrets in code**: Never commit secrets, credentials, API keys, or
  tokens. Do not include API keys in client-side bundles.
* **Log safety**: Never log credentials, authorization headers, or user PII.
* **Input validation**: Treat all URL parameters, request bodies, and model
  outputs as untrusted. Sanitize before rendering HTML (XSS prevention) or
  navigating (open redirect prevention).
* **GitHub Actions**: Pin third-party actions to a full commit SHA with the
  version tag in a trailing comment.

---

## 8. Data Commons Pipeline Conventions

* **Server-side payload shaping**: Reshape and prune heavy Data Commons
  responses on the server before sending to the client. Keep the client light.
* **Data integrity**: Sort observations ascending by date before calculating
  deltas or charting. Filter nullish values before arithmetic.
* **Place-variable binding**: When falling back to a parent place, query the
  fallback variable against the fallback place to prevent false "no data".

---

## 9. Frontend & Accessibility

* **Semantic HTML**: Use `<button>` for actions, `<a>` for navigation. Do not
  attach click listeners to `<div>` or `<span>` without button semantics.
* **Keyboard navigation**: All interactive elements must be focusable with
  `Tab`, operable with `Enter`/`Space`, and provide visible focus rings.
* **Accessible labels**: Buttons without visible text (e.g. icon buttons) must
  have an `aria-label`. Form inputs must have associated `<label>` tags.
* **Motion**: Respect `prefers-reduced-motion` for decorative animations.
