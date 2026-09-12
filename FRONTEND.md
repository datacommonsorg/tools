# Frontend Conventions

> [!NOTE]
> This document covers **frontend web application development** only: React,
> component structure, motion, and accessibility. General engineering rules —
> simplicity, file organization, naming, TypeScript language rules, testing,
> error handling, security — live in
> [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) and apply here too.
>
> **Styling stacks are app-level.** Each app states its stack and its rules in
> its own `FRONTEND.md`: [`dataweaver/FRONTEND.md`](dataweaver/FRONTEND.md) for
> SCSS modules, [`narratives/FRONTEND.md`](narratives/FRONTEND.md) for Tailwind.
> An app copy augments this document; it does not replace it. Where the two
> differ, the app copy takes precedence. Read the app copy as well as this one.

---

## 1. Component architecture

Structure components from lowest level to highest. Composition flows upward:

* **Primitives**: Thin wrappers over a single platform or third-party concern
  (e.g., links, icons, images). No business logic, minimal styling. Always go
  through these instead of raw HTML tags (`<a>`, `<img>`). Typographic HTML
  elements (such as `<h1>`–`<h6>`, `<p>`, `<span>`, etc.) are allowed directly
  unless a dedicated project text-wrapper primitive exists.
* **Elements**: Generic, reusable, presentational building blocks (e.g.,
  buttons, tabs). Self-contained, no feature or business logic. Flat by
  default.
* **Scopes**: Feature- or page-scoped compositions that assemble primitives and
  elements into a specific view. A scope owns its sub-components (placed in its
  own folder).
* **Foundations**: App-level infrastructure and cross-cutting providers that
  render little or no UI but wrap the whole tree near the root.

Decide placement by reuse and concern: a single platform concern → primitive;
reusable presentational UI → element; tied to one view → that scope; app-wide
service or provider → foundation.

Component files follow the general naming rules (`snake_case` file names,
`PascalCase` identifiers, category-first composition) and the flat-by-default
rule in [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) §3 — promote a component
to a folder only once it actually gains a sub-component used solely by it:

```
elements/
  button/
    button.tsx
    icon.tsx           # used only by button
  card.tsx
```

---

## 2. Rendering and data flow

The first two rules apply to apps that render on a server. The third applies to
every app.

* **Server-First Default (FCP/LCP)**: Deliver critical page structure and
  content from the server to minimize Largest (LCP) and First Contentful Paint
  (FCP) times. This ensures users see fully rendered content immediately,
  rather than waiting for client JavaScript bundles to execute.
* **Isolate Interactivity**: Push client-side rendering (CSR) out to the leaves
  of the component tree. Only use client execution for interactive state,
  user-specific data, and browser APIs.
* **Server-to-Client Data Flow**: Treat the server as the data resolution
  source. Fetch data (either during the initial server load or dynamically via
  server-side API endpoints) and resolve environment secrets on the server,
  then pass them downstream to Client Components as read-only, serialized
  props. Client Components must never import server-side modules or access
  private environment variables directly.

---

## 3. React conventions

* **Component Return Styles**: Prefer an explicit `return` block for React
  components. Implicit arrow returns are permitted for stateless, simple, or
  single-line components (such as SVG icon wrappers).
* **Props Interfaces**: Component props are an `interface` named
  `ComponentNameProps` (e.g., `interface CardProps`).
* **Clean JSX Logic**: Avoid complex nested ternaries in JSX. Extract logical
  blocks into constants, helper variables, or mapper objects.
* **Ordering Conventions**:
  * **Props Destructuring**: Destructure props in the same order as defined in
    the `interface`, so reviewers can diff props against the type at a glance.
  * **Ref/State Hooks**: Declare DOM-bound variables (hooks, refs, IDs) in the
    order they render in the JSX tree.
* **Untrusted Client Input**: URL hashes and search parameters
  (`window.location.hash`, `window.location.search`) are untrusted input.
  Sanitize them before passing them into hooks, renderers, or navigation — see
  [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) §11.

---

## 4. Styling Conventions

### 4.1 One stack per app

Each app picks a single styling stack and states it in its own `FRONTEND.md`.
Do not mix stacks within one app: it inflates the bundle, duplicates styling,
and forces every contributor to hold two systems in their head. Shared design
tokens remain the single source of truth regardless of stack.

How variants and state are expressed — `data-*` attributes, utility class
composition, or otherwise — follows from the stack, so each app states it in
its own `FRONTEND.md`.

### 4.2 CSS Best Practices

* **Cropping**: Prefer `overflow: clip` over `overflow: hidden` when you only
  need to crop (this avoids creating unnecessary scroll containers or new
  stacking contexts).
* **Sibling Overlap**: Prefer **grid-stack** (`display: grid` +
  `grid-area: 1 / 1`) over absolute positioning to overlap sibling elements.
* **Breakpoint Property Removal**: Use `unset`, not a hardcoded zero, when
  removing a property at a responsive breakpoint.
* **Don't Restate the Reset**: Do not restate styles already neutralized by a
  global reset (such as margins, button chrome, outline, padding, etc.).
* **Focus Outlines**: Override focus offsets via `--outline-offset` (e.g., 2px
  or -3px); never override the `outline` property itself.

---

## 5. Performance & Motion

* **Compositor-Only Animations**: Restrict high-frequency animations to
  `transform` and `opacity` to avoid triggering document layout cascades or
  browser paint cycles.
* **Reduced Motion**: Respect system-level user preferences for reduced motion.
  * In CSS, gate animations on the app's reduced-motion mechanism.
  * In React/JS, gate animation states using a `prefers-motion` hook check.
* **Batch DOM Actions**: Perform reads (e.g., `getBoundingClientRect()`)
  separately from writes to avoid style recalculation thrashing, especially in
  scroll handlers.
* **React Motion (`motion/react`)**:
  * Use the lightweight, lazy-loaded export `m.*` rather than the standard
    `motion.*`.
  * Export eased constants (e.g., `EASE_OUT`) from design tokens.
  * Gate Motion props on a `prefers-motion` check (e.g., via a conditional
    spread of `animate` / `transition` props) so reduced-motion users render
    the static resting state.

---

## 6. Accessibility (a11y)

Target WCAG 2.2 AA compliance natively:

* **Semantic HTML**: Use proper tags (`<button type="button">`, `<article>`,
  `<section>`, `<Link>`, `<ul>`/`<li>`). Avoid adding interactive `onClick`
  handlers to `<div>` or `<span>` elements.
* **Aria Labels**: Any visual-only element or button (such as icon-only
  actions) must feature an explicit `aria-label`, with the internal visual
  content hidden via `aria-hidden="true"`.
* **Keyboard Navigation**: Ensure all controls are fully focusable and usable
  via keyboard shortcuts (Space / Enter). Do not remove focus indicator rings
  unless providing a `:focus-visible` alternative.
* **Touch Targets**: Interactive controls must have a minimum clickable area of
  44×44 CSS pixels.
* **Loading Regions**: Busy states must feature `role="status"` with a visually
  hidden text label, while the visual placeholder skeleton is hidden via
  `aria-hidden="true"`.
* **Visual Design**: Never convey state or information using color alone. Check
  color contrast ratios (minimum 4.5:1 for body copy, 3:1 for large text/UI).

---

## 7. Frontend Checklist

### 7.1 Never

* Render raw `<a>` or framework-specific link elements directly (always use
  project primitives/wrappers).
* Hardcode pixel sizes or hex colors (use token variables).
* Use bare hex or `rgb(0 0 0 / ...)` for translucency (always anchor to a
  semantic token/variable).
* Restate styles already neutralized by global CSS resets.
* Use raw `z-index` numbers (use z-index variables or stacks).
* Remove focus outline indicator rings without providing a `:focus-visible`
  alternative.
* Mark a focusable interactive element as `aria-hidden="true"`.
* Use raw standard `motion.*` elements (use lazy `m.*` elements).

### 7.2 Always

* Consume design values exclusively from tokens.
* Gate motion-bearing transitions on a reduced-motion check.
* Give icon-only interactive controls an `aria-label` and mark inner icons as
  `aria-hidden="true"`.
* Keep the interface premium and polished: no default browser colors, unstyled
  elements, or janky animations.
* Run the app's lint, test, and build commands before pushing UI changes (see
  [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) §16).
