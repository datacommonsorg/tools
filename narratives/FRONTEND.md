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
- **Theme values come from CSS custom properties** written as
  `var(--theme-*, <fallback>)`. The fallback after the comma is the Base Data
  Commons default, overridden when `--theme-*` properties are defined in
  `<style id="theme-tokens">` in `index.html`. Never hardcode a theme color.
- **Instance configuration comes from `#instance-config`** in `index.html`.
  Components read `instanceName`, `logoUrl`, `logoText`, `logoAlt`, `headline`,
  `tagline`, `suggestions`, `navigation`, `metrics`, `thinkingIndicatorUrl`, and
  `doneIndicatorUrl` synchronously via `getInstanceConfig()` in
  `src/config/instance_config.ts`, which parses
  `<script id="instance-config" type="application/json">` and falls back to the
  Base Data Commons defaults when the tag is empty.
- **Variants and state are expressed as conditional utility classes**, the
  Tailwind idiom — not `data-*` attributes, which belong to a stylesheet-driven
  stack. Lift any condition more complex than a single ternary out of the JSX
  into a named constant or lookup object.
