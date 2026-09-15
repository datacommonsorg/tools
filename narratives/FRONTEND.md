# Frontend Conventions — narratives

> [!IMPORTANT]
> This document covers **narratives frontend** work only. It augments the
> repository-root [`FRONTEND.md`](../FRONTEND.md); it does not replace it. Where
> the two differ, this document takes precedence.
> General engineering rules — simplicity, file organization, naming, TypeScript
> language rules, error handling, testing, security — live in
> [`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md) at the repository root and
> apply here in full. Narratives has no local coding-guidelines copy, and no
> app-level `AGENTS.md`.

## 1. Styling — Tailwind v4

Tailwind is the styling stack for this app. No SCSS, no CSS modules, no inline
styles.

- **Standard utilities only** (`w-px`, `mt-0.5`). Avoid arbitrary values
  (`h-[3px]`) unless the dimension is genuinely non-standard.
- **No inline hex.** Reusable colors, fonts, and assets belong in the Tailwind
  theme in `src/index.css`.
- **Brand values come from runtime CSS variables** —
  `var(--brand-*, <fallback>)` — injected from the instance's `branding.json`.
  The fallback after the comma is the shipped design default. Never hardcode a
  brand color.
- **Variants and state are expressed as conditional utility classes**, the
  Tailwind idiom — not `data-*` attributes, which belong to a stylesheet-driven
  stack. Lift any condition more complex than a single ternary out of the JSX
  into a named constant or lookup object.
