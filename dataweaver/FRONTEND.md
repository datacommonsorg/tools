# Frontend Conventions

The authoritative reference for writing React + SCSS in this project. Read this
before touching any component, hook, or stylesheet.

These conventions follow the same shape as our other projects, but this is a
**Google-style-guide project**, so several rules are inverted by the linting
setup. The Google-specific differences:

| Topic | This project (Google) | Enforced by |
|---|---|---|
| Object shapes | **`interface` over `type`** (props named `ComponentNameProps`) | Biome `useConsistentTypeDefinitions: interface` |
| Indentation | **2 spaces** (no tabs) | Biome / Stylelint |
| Translucent colour | **`rgb(var(--color-x) / <alpha>)`** — tokens are CSS variables | convention |
| Token source | **`@package/tokens`** (`/css`, `/scss`, `/ts`) — not in-app generated | convention |
| Class names | **kebab-case** | Stylelint `selector-class-pattern` |

Full rule sources: [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html)
and [Google HTML/CSS Style Guide](https://google.github.io/styleguide/htmlcssguide.html),
enforced via `biome.json` and `stylelint.config.mjs`.

---

## 1. File layout

| Component | Location |
|---|---|
| Primitive (wrapper over one platform / third-party concern) | `components/primitives/<name>.tsx`, or grouped by category — e.g. `components/primitives/icons/<name>.tsx` |
| Element (generic, reusable building block) | `components/elements/<name>/<name>.tsx` + `.module.scss` |
| Scope (feature- / page-scoped composition) | `components/scopes/<name>/<name>.tsx` |
| Scope-local subcomponent (used only by that scope) | nested in the scope folder, e.g. `components/scopes/tldraw/card/card.tsx` |
| Foundation (app-level provider / service / global embed) | `components/foundations/<name>.tsx`, mounted once near the root |

Layered low → high: **primitives → elements → scopes**, with **foundations**
wrapping the tree from the root. Composition flows upward; decide placement by
reuse and concern (one platform concern → primitive; reusable presentational UI
→ element; tied to one view → that scope; app-wide service → foundation). See
[AGENTS.md](AGENTS.md) for the full description of each category.

- **Kebab-case** file names; **PascalCase** component identifiers
  (`card-text.tsx` → `CardText`).
- Every `.tsx` pairs with a co-located `.module.scss`. No styled-jsx, no
  Tailwind, no inline styles (CSS custom properties via `style={{}}` are fine
  for index-driven values only — see §3.5).
- Keep a component in the narrowest scope that owns it. A component used only
  inside one scope lives in that scope's folder, not in `elements/`.

---

## 2. TypeScript

- **`interface` over `type`** for object shapes. Name a component's props
  `ComponentNameProps` (`interface CardProps`). Unions, tuples, mapped and
  function types stay `type`.
- **Named exports only** — `export default` is allowed only in `src/app/**`
  (Next.js route files) and `*.config.*`.
- **`import type`** for type-only imports; **`export type`** for type-only
  re-exports.
- **Components use an explicit `return` block** — `() => { return ( … ); }`,
  never an implicit arrow return, even for one-line JSX. Implicit returns are
  fine for non-component helpers whose body fits on one line.
- Prefer arrow functions; only mark a function `async` when it `await`s.
- **No `any`** — use `unknown` and narrow. If unavoidable, suppress the single
  line with a comment, never relax the rule globally.
- `===` / `!==` only; `const` by default; **braced** control statements.
- **Single quotes** for JS / TS strings (Biome). SCSS strings use double quotes,
  plain `.css` single — see §3.1.
- **80-column lines** — keep code and prose (incl. this doc and Markdown) at
  ≤ 80 chars. Biome (JS / TS / JSON) and Prettier (SCSS) reflow on format; wrap
  long lines rather than letting them run. The only exceptions are unbreakable
  tokens (long URLs, import paths).
- No relative parent imports (`../`) — use the `~/` alias (`~/* → apps/web/src/*`).
- Destructure props **in the same order as the interface** so reviewers can diff
  props against the type at a glance.
- Declare **DOM-bound variables (refs, IDs) in the order they appear in the
  rendered tree**, so the hooks block can be read top-to-bottom against the JSX.
- Prefer full names (`index` not `i`, `calculateTotal` not `calcTotal`). Prefix
  booleans with `is` / `has` / `should` (`isLoading`, `hasFooter`).
- Add JSDoc where intent is non-obvious.

---

## 3. SCSS

CSS Modules only (`*.module.scss`), imported as `import s from './x.module.scss'`.

`~/styles/includes` (breakpoint / helper / z-index mixins) is **auto-injected**
into every module via `next.config.ts` `additionalData` — do **not** re-`@use`
it. Only `@use` files that aren't part of includes (e.g.
`@use "~/styles/typography.module" as typography;`).

### 3.1 Selectors & formatting

- Class names are **kebab-case** (e.g. `.card`, `.icon`, `.actions`). For
  multi-word classes, access them in JSX via `s['card-text']`; prefer concise
  single-word names where the role is clear.
- 2-space indent. SCSS strings use double quotes; plain `.css` uses single
  quotes (Biome owns `.css`, Stylelint owns `.scss`).
- No redundant nesting selectors (Stylelint enforces).

### 3.2 Class naming vocabulary

- **Root element = `.container`.** One per file; identity comes from the file
  name and `data-*` attributes, not a unique root class.
- **Layout wrappers = `<noun>-container`** (e.g. `.assets-container`). Never
  `wrapper` / `outer` / `inner`.
- **Bare leaf class only when it renders a prop of the same name** —
  `<h2 className={s.title}>{title}</h2>`. Otherwise use a `<noun>-container` or
  an element-prefixed class.
- **Multiple buttons / icons → element-prefixed kebab**: `.button-close`,
  `.icon-arrow-right` (read left-to-right: "a button that closes").

### 3.3 Variants & state via `data-*`

Drive visual variants and boolean state through `data-*` attributes on the
container — never through className flags:

```tsx
<article className={s.container} data-state={state} data-has-footer={hasFooter}>
```

```scss
.container[data-state="selected"] .card { … }
```

### 3.4 Design tokens

Tokens come from `@package/tokens` (see [AGENTS.md](AGENTS.md)):

- **Colour**: `rgb(var(--color-name))`; translucent: `rgb(var(--color-name) / 50%)`.
  Never a bare hex or `rgb(0 0 0 / …)` — always anchor to a `--color-*` variable.
- **Breakpoints (SCSS, build-time)**: `@include breakpoint(tablet|laptop|desktop)`.
- **Z-index**: `$z-index-*` (ordered stack in `_z-indices.module.scss`) — never a
  raw number.
- **Easing (SCSS)**: `$ease-linear` / `$ease-out` / `$ease-in` / `$ease-in-out`.

If a design value has no matching token, flag it — don't introduce a one-off
constant without discussion.

### 3.5 Index-driven values

Pass index-based values as CSS custom properties via `style`, never as class
permutations: `<li style={{ '--row': index + 1 }}>` → `grid-row: var(--row);`.

### 3.6 Responsiveness — mobile-first

Base styles target mobile; layer up with `@include breakpoint(tablet)` (768px+),
`laptop` (1280px+), `desktop` (1600px+).

### 3.7 Motion

Always wrap animation / transition styles in `@include prefers-motion { … }` so
reduced-motion users get a static rendering. Animate **`transform` / `opacity`
only** for per-frame values (compositor-only; skip layout/paint).

### 3.8 Misc

- Prefer `overflow: clip` over `overflow: hidden` when you only need to crop
  (no scroll container / new stacking context).
- Prefer **grid-stack** (`display: grid` + `grid-area: 1 / 1`) over absolute
  positioning to overlap siblings.
- When removing a property at a breakpoint, use `unset`, not a hardcoded zero.
- **Don't restate the reset.** `styles/core/_reset.scss` already neutralises
  margins, `button` chrome, `a` decoration, list bullets, etc. Check it before
  adding `padding: 0` / `border: 0` / `background: none`.
- Override focus offset via `--outline-offset` (`-default` 2px / `-inset` -3px);
  never override `outline` itself.
- Typography mixins live in `~/styles/typography.module.scss` — `@use` it where
  needed (it isn't part of the auto-injected includes).
- Cascade layers, low → high: `reset, root, base, primitive` (`~/styles/layers.css`).

---

## 4. Primitives & hooks — use these, don't reimplement

| Need | Use | Import |
|---|---|---|
| Link (internal / external / anchor) | `<Link href={…}>…</Link>` | `~/components/primitives/link` |
| Compose class names | `mergeClassNames(…)` | `~/functions/merge-class-names` |
| Match a breakpoint / media query | `useMatchMedia("tablet" \| "prefers-motion" \| …)` | `~/hooks/use-match-media` |

`<Link />` derives internal (`NextLink`) vs external (`target="_blank"` +
`rel="noopener noreferrer"`) from `href` / `isExternal` — never pass `target`
/ `rel` yourself, and never render a raw `<a>` / `NextLink`.

---

## 5. Motion / animation

The library is `motion/react`. The `MotionProvider` foundation
(`foundations/motion-provider`) wires `LazyMotion` (`strict`, `domMax`) at the
root layout, so use **`m.*`**, never `motion.*`.

JS-side easing constants (typed): import `EASE_LINEAR` / `EASE_OUT` / `EASE_IN`
/ `EASE_IN_OUT` from `@package/tokens/ts`. SCSS equivalents: `$ease-*`.

Gate motion in CSS with `@include prefers-motion`. For Motion props, gate the
animation block on `useMatchMedia("prefers-motion")` via a conditional spread so
reduced-motion users render the static resting state.

---

## 6. Performance

- Animate `transform` / `opacity` only for per-frame values — both stay on the
  compositor.
- Don't drive per-frame transforms through a CSS variable consumed by many
  descendants (cascading style recalc) — pass the `MotionValue` to an `m.*`
  element's `style`.
- Batch DOM reads before writes; keep `getBoundingClientRect()` / `offsetWidth`
  out of scroll / animation hot paths.

---

## 7. Accessibility

Target WCAG 2.2 AA. Build it in, don't bolt it on.

- **Semantic HTML first.** `<section>` for sections, `<article>` for
  self-contained content (a card), `<button type="button">` for actions,
  `<a>` via `<Link />` for navigation, `<h1>`–`<h6>` for headings (never a
  styled `<div>`), `<ul>`/`<ol>` + `<li>` for lists. Never `<div onClick>`.
- **Headings**: one `<h1>` per page; don't skip levels; visual size ≠ level.
- **Icon-only buttons / links** need `aria-label`; the inner icon is
  `aria-hidden`.
- **Focus**: every interactive element reachable via Tab and operable via
  Enter / Space; never remove the focus outline (restyle via `:focus-visible`);
  tab order matches visual order; no `tabindex ≥ 1`.
- **Touch targets** ≥ 44×44 CSS px (pad or use a pseudo-element).
- **Loading regions** use `role="status"` with a visually-hidden label
  (`@include screen-reader-only`) and `aria-hidden` on the visual skeleton.
- Never convey state with colour alone; check contrast (4.5:1 body, 3:1 large /
  UI).

---

## 8. Rules (never / always)

**Never:**
- Use `type` for an object shape (use `interface`); name props anything but
  `ComponentNameProps`.
- `export default` outside `src/app/**` / `*.config.*`.
- Use `any` (suppress one line with a comment if truly unavoidable).
- Relative parent imports (`../`) — use `~/`.
- Hardcode a colour / size / spacing that has a token; use a bare hex or
  `rgb(0 0 0 / …)` for translucency — anchor to `rgb(var(--color-x) / a)`.
- Restate the reset in a component module.
- Drive variants via className flags — use `data-*`.
- Raw `<a>` / `NextLink` / `<div onClick>`; remove the focus outline; mark a
  focusable element `aria-hidden`.
- A raw `z-index` number, or `motion.*` (use `m.*`).

**Always:**
- Named exports; `import type` for type-only imports; explicit `return` block in
  components; props destructured in interface order.
- Co-locate `.tsx` with `.module.scss`; kebab class names; `.container` root.
- Keep lines ≤ 80 columns (code and prose).
- Consume tokens from `@package/tokens`; wrap motion-bearing SCSS in
  `@include prefers-motion`.
- Icon-only controls get `aria-label`, inner icon `aria-hidden`.
- Run `pnpm lint` (and `pnpm build` for UI changes) before done.
