# Data Commons Tools — agent guide

Repository-level entry point for coding agents. It contains no conventions of
its own: it says which document governs what, and where each application's
guide lives.

## Applications

| Directory | What it is | App guide |
|---|---|---|
| `dataweaver/` | Next.js 16 / React 19 app (pnpm workspaces) | [`dataweaver/AGENTS.md`](dataweaver/AGENTS.md) |
| `narratives/` | React + Vite SPA and the Python server that hosts it | [`narratives/AGENTS.md`](narratives/AGENTS.md) |
| `bigtable_automation/`, `gcf/` | Older standalone tools; no app guide | — |

`narratives/` splits into two toolchains: npm for the SPA in `ui/`, and uv
for the Python app plane in `agent/`. Its guide covers both; do not assume
the npm commands are the whole gate.

## Which document governs what

| Document | Scope |
|---|---|
| [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) | General engineering rules, all languages, all apps |
| [`FRONTEND.md`](FRONTEND.md) | Frontend/UI: React, components, motion, accessibility |
| `<app>/AGENTS.md` | App layout, commands, app-specific conventions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution process, PR expectations, review policy |
| [`CONTINUOUS_INTEGRATION.md`](CONTINUOUS_INTEGRATION.md) | CI orchestrator and how to wire a new app into it |
| [`.agent/skills/datacommons-pr-review/SKILL.md`](.agent/skills/datacommons-pr-review/SKILL.md) | Pull request review workflow and verification checklist |

## Resolution rule

For `CODING_GUIDELINES.md` and `FRONTEND.md`, **read the root copy, then the
copy in the application directory you are working in, where it has one.** An
application-level copy augments the root document; it does not replace it.
Where the two differ, the application-level copy takes precedence.

Today: each app carries its own `FRONTEND.md`, holding the styling stack it
uses — SCSS modules in `dataweaver/`, Tailwind in `narratives/`. Neither app has
a local `CODING_GUIDELINES.md`, so the root copy governs both.

## Before you start

1. Read [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md).
2. Read the frontend document that applies, if the work touches UI.
3. Read the `AGENTS.md` of the application you are changing, where it has one,
   and use the commands documented there — do not guess build, test, or lint
   commands.
4. Run that application's lint, test, and build before submitting.
5. When reviewing a pull request or branch diff, follow
   [`.agent/skills/datacommons-pr-review/SKILL.md`](.agent/skills/datacommons-pr-review/SKILL.md).
