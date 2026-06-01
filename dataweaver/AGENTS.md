# dataweaver — agent guide

Root of the `/dataweaver` directory, managed with [pnpm workspaces](https://pnpm.io/workspaces).
It sits within a larger monorepo, so all paths and commands here are relative to
`/dataweaver`, not that outer repo.

This file is the source of truth for project conventions, imported by each
tool's agent entry point so every assistant reads the same rules.

## Layout

- `apps/web` — Next.js 16 app (App Router, React 19, Turbopack).
- `packages/tokens` — design tokens (JSON → generated CSS / SCSS / TS), consumed as `@package/tokens`.

## Commands

Run from the root of the `/dataweaver` directory:

- `corepack enable && pnpm i` — install (the pnpm version is pinned via `packageManager`).
- `pnpm dev` — run apps in dev mode.
- `pnpm build` — build all apps.
- `pnpm lint` — type-check + Biome + Stylelint.
- `pnpm fix` — auto-fix Biome + Stylelint.
- `pnpm generate:tokens` — regenerate `packages/tokens/dist/` from `packages/tokens/src/*.json`.

Run `pnpm lint` (and `pnpm build` for UI changes) before considering work done.

## Code style

- **TypeScript** follows the [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html), enforced via Biome (`biome.json`).
- **CSS / SCSS** follow the [Google HTML/CSS Style Guide](https://google.github.io/styleguide/htmlcssguide.html): Stylelint for `.scss` (`stylelint.config.mjs`), Biome for plain `.css`.
- **File naming** — use `dash-case` for all Next.js routing within `apps/web/src/app` (route segments, `page.tsx`, dynamic params, etc.) and `snake_case` for every other file.

## Frontend

Before writing any React component, SCSS module, or front-end utility, read
[`FRONTEND.md`](FRONTEND.md) — the authoritative reference for TypeScript, SCSS,
primitives, motion, performance, and accessibility conventions.

## Components (`apps/web/src/components`)

Four categories, layered low → high. Composition flows upward (scopes compose
elements compose primitives); `foundations` wrap the whole tree from the root.

- **`primitives/`** — the lowest-level building blocks: thin wrappers over a
  single platform / third-party concern (a link, an icon, an image, rich text).
  No business logic, minimal styling. Always go through these instead of raw
  `<a>` / `<img>` / `NextLink` / inline `<svg>`. _e.g._ `primitives/link`,
  `primitives/icons/*`.
- **`elements/`** — generic, reusable, presentational building blocks composed
  from primitives (a button, a tabs control). Self-contained, no feature or
  business logic, usable anywhere. _e.g._ `elements/button`.
- **`scopes/`** — feature- or page-scoped compositions that assemble primitives
  and elements into a specific view. A scope **owns its sub-components**: pieces
  used only by that scope live in its folder, not in `elements/`. _e.g._
  `scopes/page-home` and `scopes/tldraw`.
- **`foundations/`** — app-level infrastructure and cross-cutting providers /
  services that the rest of the tree depends on but that render little or no UI
  of their own: context providers, motion / scroll providers, analytics, global
  embeds, dev tooling. Mounted once near the root (`app/layout.tsx`). _e.g._
  `foundations/motion-provider` (wraps the tree in motion's `LazyMotion`).

Decide placement by reuse and concern: a single platform concern → `primitive`;
reusable presentational UI → `element`; tied to one view → that `scope`;
app-wide service / provider → `foundation`.

## Design tokens (`@package/tokens`)

Source: `packages/tokens/src/*.json`. Edit those and run `pnpm generate:tokens`;
never edit `packages/tokens/dist/**` (generated).

- **Colors** → `@package/tokens/css` (imported once in `core.scss`): `:root` custom properties as space-separated channels. Use as `rgb(var(--color-name))`; alpha as `rgb(var(--color-name) / 50%)`. Names are **semantic, not literal** (e.g. `surface-base` and `text-primary`), defined in `colors.json` as `[r, g, b]` — this is the theme contract partners override, so the app never references raw palette names like `blue`.
- **Breakpoints** → `@package/tokens/scss` (build-time SCSS for `@media`) and `@package/tokens/ts` (`BREAKPOINT_*`). Not CSS variables — `var()` is invalid in media-query conditions.
- **Eases / color values in JS** → `@package/tokens/ts` (`EASE_*`, `COLORS`).

Add new colors to `colors.json`, breakpoints to `variables.json`, eases to `eases.json`, then regenerate.

## Verify

`pnpm lint` for every change; `pnpm build` and a manual check for UI changes.

## Self-maintenance

When a change affects project structure, dependencies, commands, or
architecture, update this file, [`FRONTEND.md`](FRONTEND.md), and `README.md` to
match. Keep `AGENTS.md` / `FRONTEND.md` as the technical source of truth and
`README.md` as user-facing docs. The per-tool agent entry points import this
file — edit conventions here, not in those.
