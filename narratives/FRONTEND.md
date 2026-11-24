# Frontend Conventions — narratives

> [!IMPORTANT]
> This document covers **narratives frontend** work only. It augments the
> repository-root [`FRONTEND.md`](../FRONTEND.md); it does not replace it. Where
> the two differ, this document takes precedence.
> General engineering rules — simplicity, file organization, software design and
> module boundaries, naming, TypeScript language rules, error handling, testing,
> security — live in [`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md) at the
> repository root and apply here in full. Narratives has no local
> coding-guidelines copy; project layout, commands, and workflows are in
> [`AGENTS.md`](AGENTS.md).

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
  Components read `instanceName`, `logoUrl`, `logoText`, `logoAlt`, `logoHref`,
  `headline`, `tagline`, `taglineLink`, `suggestions`, `navigation`, `metrics`,
  `thinkingIndicatorUrl`, and `doneIndicatorUrl` synchronously via
  `getInstanceConfig()` in `src/config/instance_config.ts`, which parses
  `<script id="instance-config" type="application/json">` and falls back to the
  Base Data Commons defaults when the tag is empty.
- **Runtime settings come from `#runtime-config`** in `index.html`.
  Components read the chat availability (`isChatEnabled`, `unavailableTitle`,
  `unavailableMessage`), chart hosts (`webComponentUrl`,
  `webComponentApiRoot`), and optional reCAPTCHA Enterprise site keys
  (`recaptchaSessionSiteKey`, `recaptchaCheckboxSiteKey`) synchronously via
  `getRuntimeConfig()` in `src/config/runtime_config.ts`, which defaults chat
  to enabled and optional hosts and site keys to `""` when the tag is empty,
  disables chat when its JSON is malformed, and resolves missing or invalid
  hosts or site keys to `""` without affecting chat. Under `pnpm dev:ui`, the
  Vite dev server copies the element from the agent at `AGENT_URL`; agent
  values take precedence, and `RECAPTCHA_SESSION_SITE_KEY` /
  `RECAPTCHA_CHECKBOX_SITE_KEY` from `narratives/.env.local` act as a dev-only
  fallback when the agent omits them or cannot be reached.
- **Variants and state are expressed as conditional utility classes**, the
  Tailwind idiom — not `data-*` attributes, which belong to a stylesheet-driven
  stack. Lift any condition more complex than a single ternary out of the JSX
  into a named constant or lookup object.

## 2. Imports

- **Import through the `@/` alias, never a relative path:**
  `@/src/hooks/use_sse_chat`, not `./use_sse_chat` or `../hooks/use_sse_chat`.
  This is stricter than [`CODING_GUIDELINES.md`](../CODING_GUIDELINES.md)
  §3.1, which bans only `../`. Biome's `noRestrictedImports` enforces it.
- Config files (`*.config.*`) and `scripts/**` are exempt. Vite loads
  `ui/vite.config.ts` before the alias exists, and scripts run directly in
  Node, where `@/` is not defined.
