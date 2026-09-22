---
name: datacommons-pr-review
description: >-
  Pull request review workflow for the Data Commons tools repository
  (DataWeaver and Narratives). Covers PR discovery and local checkout, the
  standards audit, diff hygiene, local verification, PR
  description alignment, severity-tagged reporting, and teardown. Engineering
  standards themselves are NOT restated here — they live in the repository's
  own documents.
---

# Data Commons PR Review

The standard procedure for reviewing Pull Requests in `datacommonsorg/tools`
(`dataweaver/`, `narratives/`). Work the sections in order.

> [!IMPORTANT]
> **This skill contains review *mechanics* only.** Every engineering standard
> — simplicity, naming, structure, TypeScript/Python rules, error handling,
> testing, security, the Data Commons pipeline conventions, documentation, PR
> hygiene — is defined in the repository and is the authoritative source.

> [!IMPORTANT]
> **Reviewing is not fixing.** Do not edit the code, do not offer to apply
> fixes, and do not ask whether the changes should be applied. A review
> evaluates and prescribes: name the flaw, prove it, and state the exact fix.
> Implementing is a separate task that starts only when explicitly requested.

## 0. Authoritative standards (read before reviewing)

Resolution rule: for `CODING_GUIDELINES.md` and `FRONTEND.md`, **read the root
copy, then the copy in the application directory being changed, where it has
one.** An application-level copy augments the root document; it does not
replace it. Where the two differ, the application-level copy takes precedence.

| Document | What it governs |
|---|---|
| `AGENTS.md` (root) | Repo map, document resolution rule |
| `CODING_GUIDELINES.md` | All general engineering rules, all languages |
| `FRONTEND.md` | React, styling, motion, accessibility |
| `<app>/AGENTS.md` | Layout, commands, app-specific conventions |
| `CONTRIBUTING.md` | PR title/description/testing/size expectations |
| `.github/pull_request_template.md` | The canonical PR description structure |
| `CONTINUOUS_INTEGRATION.md` | CI orchestrator, required status check |

Today: each app carries its own `FRONTEND.md`, holding the styling stack it
uses — SCSS modules in `dataweaver/`, Tailwind in `narratives/`. Neither app has
a local `CODING_GUIDELINES.md`, so the root copy governs both.

---

## 1. Discovery and local checkout

Always bring the branch down locally; never review from the web diff alone.

```bash
# Intent, prior discussion, and bot feedback
gh pr view <PR>
gh pr view <PR> --comments

# Local checkout and the true base diff
gh pr checkout <PR>
git log -n 5 --oneline
git diff <BASE>...HEAD --stat
git diff --name-status <BASE>...HEAD
```

When reviewing a local branch rather than a PR, diff against the upstream
base, not `origin`: `git diff upstream/main...HEAD`.

Checklist:

* Establish author intent, linked issues, and explicitly deferred follow-ups.
* Read prior reviewer and bot comments (e.g. Gemini Code Assist) — build on
  them, do not restate them.
* List the changed files by layer: prompts/config, agent/server, client, UI,
  tests, infra.
* Read heavily modified files **in full**, not just the diff hunks —
  architectural drift is invisible in a hunk.
* Read the `AGENTS.md` of each app the PR touches.

---

## 2. The standards audit

Read `CODING_GUIDELINES.md`, the applicable `FRONTEND.md`, and the
`<app>/AGENTS.md` **in full** before forming an opinion. They are short enough
to read entirely, and they are the checklist: walk their sections in order and
ask, for each, whether this diff violates it. Do not work from a remembered
summary, and do not treat any list in this skill as the set of things worth
checking.

When you raise a finding, cite the document and section it comes from, so the
author can go read the rule rather than argue with the reviewer.

Three judgment calls the documents cannot make for you:

* **Precedent vs. rule.** A change that follows a bad local precedent is not
  automatically a blocker. Note it, tag `[FOLLOWUP]`, and propose the cleanup
  as a separate change rather than blocking on it.
* **Enforced vs. advisory.** If the linter already enforces a rule, do not
  spend review comments on it — spend them on what tooling cannot catch.
* **Rule vs. gap.** If the diff does something questionable that no document
  covers, say so as a judgment, not as a violation, and propose the rule if it
  is worth writing down.

---

## 3. Diff hygiene and revert candidates

Separately from correctness, list changes that should not be in this PR:

* Files containing only whitespace, re-wraps, or automated formatting.
* Comment edits with no functional consequence.
* Drive-by renames or refactors unrelated to the stated goal.
* Generated artifacts committed by accident.

Report them together as **revert candidates** so the diff can shrink in one
pass. If the PR is oversized or mixes concerns, prescribe the split explicitly
(prep/refactor → core logic + tests → wiring/UI) per `CONTRIBUTING.md`.

---

## 4. Verify locally

Never approve on reading alone when the change is executable.

1. Get the commands from the app's `AGENTS.md` — do not guess or reuse
   remembered flags.
2. Run, in order: any required code generation, the unit tests, the
   type-check/lint, and — for UI, dependency, or build-config changes — the
   production build.
3. Run the dev server and exercise the change for multi-layer data or UI work.
   Record what you observed, not just that it "worked".
4. Note anything that fails on the base branch too; that is a pre-existing
   condition, not a finding against this PR.

---

## 5. PR description

The repository owns the format: `.github/pull_request_template.md` defines the
structure, and `CONTRIBUTING.md` defines what each section must establish and
how it should be written. Do not propose a different shape.

Audit the description against both, and against the diff:

* **Sections filled?** Every template section answered, including the ones
  authors skip — risk and rollback, deferred follow-ups, and confirmation that
  changed goldens or fixtures are intentional.
* **Claims supported?** Anything the description asserts that the diff does not
  actually do, or does differently.
* **Changes omitted?** Anything substantive in the diff that the description
  never mentions — especially behavior changes buried in a "refactor".
* **Verification real?** Exact commands and reproducible steps, not "tested
  locally". Screenshots for UI changes, desktop and mobile.
* **Written to standard?** No first-person, no diff replay, results rather than
  test scaffolding.

Report the gaps. Draft replacement prose for the sections that need it, in the
template's existing structure.

---

## 6. Writing the findings

### Tone

Direct, specific, and prescriptive; collegial.

* **Name the flaw** in the first clause. No throat-clearing.
* **Explain the mechanism**: cite line numbers and walk the execution path that
  produces the failure.
* **Prescribe the fix**: the replacement snippet, the type, the file location.
* Where relevant, cite the governing rule by document and section title
  (`CODING_GUIDELINES.md`, "Lifecycle, concurrency, and resilience") instead of
  re-arguing it in the comment.

### Severity tags

Prefix every comment:

* `[BLOCKER]` — correctness bugs, races, unhandled failure paths, missing
  cleanup, security or secret exposure, missing regression test for a bug fix,
  architectural violations, unvetted heavyweight dependencies, misplaced files.
* `[WARNING]` — oversized or multi-concern PR, performance risk under
  realistic load.
* `[SUGGESTION]` — readability, naming, constant extraction, simplification,
  diff pruning. Non-blocking.
* `[FOLLOWUP]` — pre-existing debt the PR sits on top of; acceptable now,
  should be scheduled.
* `[NIT]` — typos, wording, trivial consistency.

### Report format

```markdown
### Summary
[2–3 sentences: intent of the PR, soundness of the approach, merge readiness.]

### PR Hygiene & Scoping
[Title, description accuracy and completeness, stated verification,
size/splitting.]

### Architecture & Layering
[Trace of the change through prompt → MCP → server → client → UI; whether
each responsibility sits at the right layer.]

### Standards & Conventions
[Findings against CODING_GUIDELINES.md / FRONTEND.md / <app>/AGENTS.md, each
citing the section.]

### Tests
[Coverage of new logic, assertion quality, edge cases and failure modes,
regression test for any bug fix.]

### Verification
[Commands run and their results; what was exercised manually.]

### Critical Findings ([BLOCKER])
- **`path/to/file:line`** — [flaw, failure trace, prescribed fix]

### Warnings ([WARNING])
### Suggestions ([SUGGESTION])
### Follow-ups ([FOLLOWUP])
### Nits ([NIT])

### Recommendation
[LGTM / LGTM with nits / Request changes — and the shortest path to green.]
```

---

## 7. Teardown

Leave the workspace exactly as you found it.

```bash
# Stop dev servers and background tasks first.
git status          # no stray scratch files, no unintended edits
git checkout main   # or the original branch
```

Report anything deliberately left behind (e.g. a review artifact) and where it
is.
