# Repository Best Practices & Conventions (Frontend Web Apps)

> [!NOTE]
> This document specifically targets **frontend web application development** in
> this repository. It serves as a comprehensive reference for code quality,
> architectural standards, and style guidelines, drawing patterns and examples
> from the repository's frontend projects. Guidelines in individual project
> folders will override this document if there are discrepancies, but must
> be called out explicitly in each project.

---

## 1. General Principles

*   **Google Style Guides**: All languages in this repository follow Google
    style guides. Examples:
    *   **TypeScript / JavaScript**: Enforced by [Google TypeScript Style
        Guide](https://google.github.io/styleguide/tsguide.html).
    *   **HTML/CSS**: Enforced by [Google HTML/CSS Style
        Guide](https://google.github.io/styleguide/htmlcssguide.html).
    *   **Go / Java / Python**: Follow their respective Google style guides.
*   **Testing Requirement**: Every new feature, component, hook, or utility
    function must be accompanied by corresponding unit/integration tests.
    Legacy code modifications should also update or introduce tests.
*   **Aesthetics and Fidelity**: The user interface must feel premium,
    responsive, and polished. Avoid default colors, unstyled elements, and
    non-smooth animations.
*   **Verification**: Always run lint checks (`pnpm lint` or equivalent), unit
    test suites (`pnpm test`), and validation builds (`pnpm build`) before
    submitting changes to ensure code cleanliness, logical correctness, and
    import safety.
*   **Documentation**: Include a file overview header explaining the scope and
    architectural responsibility of any file carrying complex workflows or
    orchestrations. Add clear annotations to public-facing functions so
    callers immediately understand the inputs, outputs, and failure cases.
    Keep documentation and markdown files wrapped to a maximum of 80 characters
    per line.

---

## 2. Project Architecture & File Layout

### 2.1 File Naming & Organization
*   **Next.js App Routing**: Use `dash-case` only inside Next.js App Router
    directories (e.g., `apps/web/src/app` for route files, pages, and layout
    files).
*   **General Files**: Use `snake_case` for all other files, including hooks,
    helpers, components, and SCSS modules (e.g., `card_chart.tsx`,
    `use_match_media.ts`).
*   **React Components**: Use `PascalCase` for React component identifiers
    (`CardChart`, not `cardChart` or `card_chart`).
*   **Path Aliases**: Do not use relative parent directory imports (`../`).
    Always use path aliases (e.g., `~/components/...`) to keep imports clean
    and refactor-friendly.

### 2.2 Naming Conventions — Category First
Lead composed names with the generic category first, then what makes it
specific. A button that closes is `button_close` (component identifier:
`ButtonClose`), an icon of an arrow is `icon_arrow_right` (component identifier:
`IconArrowRight`), and SCSS classes are element-prefixed (e.g., `.button-close`,
`.icon-arrow-right`).

This ensures:
*   **Alphabetical Grouping**: Related files and styles sit together in folder
    listings.
*   **DX Efficiency**: Fuzzy-find matches are grouped by category.
*   **Parallel Imports**: Imports align visually under the same category
    prefix.

### 2.3 Component Architecture
Structure components from lowest level to highest level. Composition flows
upward:
*   **Primitives**: Thin wrappers over a single platform or third-party concern
    (e.g., links, icons, images). No business logic, minimal styling. Always
    go through these instead of raw HTML tags (`<a>`, `<img>`). Typographic
    HTML elements (such as `<h1>`–`<h6>`, `<p>`, `<span>`, etc.) are allowed
    directly unless a dedicated project text-wrapper primitive exists.
*   **Elements**: Generic, reusable, presentational building blocks (e.g.,
    buttons, tabs). Self-contained, no feature or business logic. Flat by
    default.
*   **Scopes**: Feature- or page-scoped compositions that assemble primitives
    and elements into a specific view. A scope owns its sub-components (placed
    in its own folder).
*   **Foundations**: App-level infrastructure and cross-cutting providers that
    render little or no UI but wrap the whole tree near the root.

### 2.4 Flat vs. Nested — Avoid Early Nesting
Default to flat: a component is a pair of sibling files (`.tsx` +
`.module.scss`) sitting next to its peers:
```
elements/
  button.tsx
  button.module.scss
  card.tsx
  card.module.scss
```
Promote to a folder only when the component gains a sub-component used solely
by it. The original pair keeps its name; the sub-component lives alongside:
```
elements/
  button/
    button.tsx
    button.module.scss
    icon.tsx           # used only by button
    icon.module.scss
  card.tsx
  card.module.scss
```
A sub-component that becomes reused outside its parent gets promoted out to
its own flat pair. Don't create folders "in anticipation" of future sub-components.
Keep a component in the narrowest scope that owns it.

### 2.5 Tight Modules and Concise Functions
Break large files into small, focused modules. Both modules and individual
functions should remain tight, concise, and do exactly one thing. This directly
maximizes code reuse, simplifies unit testing, and reduces cognitive load.

---

## 3. Server-Side Rendering (SSR) vs. Client-Side Rendering (CSR)

*   **Server-First Default (FCP/LCP)**: Deliver critical page structure and
    content from the server to minimize Largest (LCP) and First Contentful 
    Paint (FCP) times. This ensures users see fully rendered content 
    immediately, rather than waiting for client JavaScript bundles to execute.
*   **Isolate Interactivity**: Push client-side rendering (CSR) out to the
    leaves of the component tree. Only use client execution for interactive
    state, user-specific data, and browser APIs.
*   **Server-to-Client Data Flow**: Treat the server as the data resolution
    source. Fetch data (either during the initial server load or dynamically
    via server-side API endpoints) and resolve environment secrets on the
    server, then pass them downstream to Client Components as read-only,
    serialized props. Client Components must never import server-side modules
    or access private environment variables directly.

---

## 4. TypeScript & React Conventions

*   **Named Exports Only**: Never use `export default` for components or
    utilities, except where required by frameworks (like Next.js pages/layouts
    in `src/app/**` or config files).
*   **`interface` over `type`**: Always use `interface` for object shapes and
    component props (named `ComponentNameProps`, e.g., `interface CardProps`).
    Use `type` only for unions, tuples, mapping types, or function types. This
    ensures compatibility with Biome linting rules.
*   **Type-Only Imports/Exports**: Use `import type` for type-only imports and
    `export type` for type-only re-exports.
*   **Component Return Styles**: Prefer an explicit `return` block for React
    components. However, implicit arrow returns are permitted for stateless,
    simple, or single-line components (such as SVG icon wrappers).
*   **Function Declarations**: Prefer arrow functions. Only mark a function
    `async` when it actually uses `await`.
*   **No `any` Types**: Never use `any`. Use `unknown` and type narrowing. If
    you must use `any` as an escape hatch, suppress only that specific line with
    a comment.
*   **Strict Comparison**: Use `===` and `!==` only. Avoid loose comparisons.
*   **Naming Clarity**: Prefer full, descriptive names (e.g., `index` not `i`,
    `calculateTotal` not `calcTotal`). Prefix booleans with `is`, `has`, or
    `should` (e.g., `isLoading`, `hasFooter`).
*   **JSDoc Documentation**: Provide JSDoc blocks for all exported hooks,
    functions, interfaces, and utilities.
*   **Clean JSX Logic**: Avoid complex nested ternaries in JSX. Extract logical
    blocks into constants, helper variables, or mapper objects.
*   **Ordering Conventions**:
    *   **Props Destructuring**: Destructure props in the same order as defined
        in the `type` or `interface`.
    *   **Ref/State Hooks**: Declare DOM-bound variables (hooks, refs, IDs) in
        the order they render in the JSX tree.

---

## 5. Styling Conventions

### 5.1 Unified Stack Recommendation
Whenever starting a new frontend app, align on a single styling stack (either
SCSS Modules or Tailwind CSS). Avoid mixing them within the same project to
prevent cognitive load, bundle inflation, and styling duplication. Shared
design tokens must remain the single source of truth.

### 5.2 SCSS Modules

*   **Setup**: Use CSS modules (`*.module.scss`), imported as `import s from
    './x.module.scss'`. Access multi-word classes via bracket notation (e.g.,
    `s['card-title']`).
*   **Root Selector & className Merging**: The root class of every stylesheet
    module must always be `.container`. Single-component identity is derived
    from the component file namespace, not a unique class name. When merging
    with an external `className` passed via props, always use the
    `mergeClassNames` utility (e.g., `className={mergeClassNames(s.container,
    className)}`).
*   **Class Naming Vocabulary**:
    *   **Layout Wrappers**: Use `<noun>-container` (e.g., `.assets-container`).
        Never use `wrapper`, `outer`, or `inner`.
    *   **Bare Leaf Class**: Only use a bare leaf class when it directly renders
        a prop of the same name (e.g., `<h2 className={s.title}>{title}</h2>`).
    *   **Multiple Elements**: Composed element classes use kebab-case and lead
        with the category prefix, e.g., `.button-close`, `.icon-arrow-right`
        (never `.close-button`, `.arrow-right-icon`).
*   **Helper Mixins**: Leverage global mixins from `styles/includes` instead of
    writing raw CSS.
    *   `@include hover { ... }`: Use instead of raw `&:hover` to prevent
        sticky hover styles on mobile.
    *   `@include breakpoint(tablet|laptop|desktop) { ... }`: Mobile-first
        responsive breakpoints.
    *   `@include screen-reader-only`: Hides elements visually but keeps them
        accessible to screen readers.
*   **Variants & State via `data-*`**: Drive visual variants and boolean state
    through `data-*` attributes on the root `.container` element rather than
    dynamic class name toggles (e.g., `<article className={s.container}
    data-is-loading={isLoading}>` mapped to
    `.container[data-is-loading="true"]`). Pass boolean variables directly:
    React automatically serializes boolean values (`true`/`false`) to strings
    (`"true"`/`"false"`) in the DOM. SCSS selectors should query the string
    value explicitly.
*   **Design Tokens & Themes**: Standardize layout and palette values using
    tokens (e.g., from `@package/tokens` or project-specific theme
    definitions).
    *   **Colors**: Use semantic token names (e.g., `rgb(var(--color-primary))`,
        `rgb(var(--theme-background) / alpha%)`) to support branding and runtime
        themes. Avoid hardcoding raw hex values or bare `rgb(0 0 0 / ...)` -
        always anchor to token variables.
    *   **Z-Index**: Use z-index variables or stacks (`$z-index-*`) rather than
        arbitrary raw numeric values to avoid layering conflicts.
*   **Index-Driven Values**: Pass index-based values as CSS custom properties
    via `style`, never as class name permutations (e.g., `<li style={{
    '--row': index + 1 }}>` and `grid-row: var(--row);`).
### 5.3 Tailwind CSS

*   **Standard Utilities Only**: Restrict styling to standard Tailwind classes
    (e.g., `w-px`, `mt-0.5`).
*   **Limit Arbitrary Values**: Avoid brackets notation (e.g., `h-[3px]`) unless
    representing a strict, non-standard layout dimension.
*   **Theme Integration**: Do not write arbitrary hex values inline. Add any
    reusable project colors, fonts, or assets to the Tailwind theme config.

### 5.4 CSS Best Practices

*   **Cropping**: Prefer `overflow: clip` over `overflow: hidden` when you only
    need to crop (this avoids creating unnecessary scroll containers or new
    stacking contexts).
*   **Sibling Overlap**: Prefer **grid-stack** (`display: grid` + `grid-area: 1
    / 1`) over absolute positioning to overlap sibling elements.
*   **Breakpoint Property Removal**: Use `unset`, not a hardcoded zero, when
    removing a property at a responsive breakpoint.
*   **Don't Restate the Reset**: Do not restate styles already neutralized by a
    global reset (such as margins, button chrome, outline, padding, etc.).
*   **Focus Outlines**: Override focus offsets via `--outline-offset` (e.g.,
    2px or -3px); never override the `outline` property itself.

---

## 6. Performance & Motion

*   **Compositor-Only Animations**: Restrict high-frequency animations to
    `transform` and `opacity` to avoid triggering document layout cascades or
    browser paint cycles.
*   **Reduced Motion**: Respect system-level user preferences for reduced
    motion.
    *   In SCSS, wrap animations in the `@include prefers-motion` mixin.
    *   In React/JS, gate animation states using a `prefers-motion` hook check.
*   **Batch DOM Actions**: Perform reads (e.g., `getBoundingClientRect()`)
    separately from writes to avoid style recalculation thrashing, especially in
    scroll handlers.
*   **React Motion (`motion/react`)**:
    *   Use the lightweight, lazy-loaded export `m.*` rather than the standard
        `motion.*`.
    *   Export eased constants (e.g., `EASE_OUT`) from design tokens.
    *   Gate Motion props on a `prefers-motion` check (e.g., via a conditional
        spread of `animate` / `transition` props) so reduced-motion users
        render the static resting state.

---

## 7. Accessibility (a11y)

Target WCAG 2.2 AA compliance natively:

*   **Semantic HTML**: Use proper tags (`<button type="button">`, `<article>`,
    `<section>`, `<Link>`, `<ul>`/`<li>`). Avoid adding interactive `onClick`
    handlers to `<div>` or `<span>` elements.
*   **Aria Labels**: Any visual-only element or button (such as icon-only
    actions) must feature an explicit `aria-label`, with the internal visual
    content hidden via `aria-hidden="true"`.
*   **Keyboard Navigation**: Ensure all controls are fully focusable and usable
    via keyboard shortcuts (Space / Enter). Do not remove focus indicator rings
    unless providing a `:focus-visible` alternative.
*   **Touch Targets**: Interactive controls must have a minimum clickable area
    of 44×44 CSS pixels.
*   **Loading Regions**: Busy states must feature `role="status"` with a
    visually hidden text label (using `@include screen-reader-only` or equivalent)
    while the visual placeholder skeleton is hidden via `aria-hidden="true"`.
*   **Visual Design**: Never convey state or information using color alone. Check
    color contrast ratios (minimum 4.5:1 for body copy, 3:1 for large text/UI).

---

## 8. Security & Input Sanitization

*   **URL Parameter Validation**: Any input ingested from URL hashes, search
    parameters, or redirects (`window.location.hash`, `window.location.search`)
    is untrusted.
*   **Sanitization**: Sanitize query values before passing them to internal
    hooks, HTML renderers, or navigation logic.
*   **Prevent Injection**: Never insert raw or unescaped parameter values
    directly into DOM-rendering blocks to guard against Cross-Site Scripting
    (XSS) and Open Redirect vulnerabilities.

---

## 9. Development Workflow Checklists

### 9.1 What to Avoid (Never Do)

#### Architecture & Imports
*   Do not use relative parent directory imports (`../`). Use path aliases
    (`~/`).
*   Do not render raw `<a>` or framework-specific link elements directly (always
    use project primitives/wrappers).

#### TypeScript & React
*   Do not use `type` for object shapes; always use `interface`.
*   Do not use default exports, except in route mappings or configuration files.
*   Do not use `any` type (suppress single line with a comment if truly
    unavoidable).

#### Styling & CSS
*   Do not hardcode pixel sizes or hex colors (use token variables).
*   Do not use bare hex or `rgb(0 0 0 / ...)` for translucency (always anchor
    to a semantic token/variable).
*   Do not restate styles already neutralized by global CSS resets.
*   Do not drive component style variants via class name flags (use `data-*`
    attributes).
*   Do not use bare `&:hover` selectors in SCSS (always gate via `@include hover`
    to prevent sticky touch states).
*   Do not use raw `z-index` numbers (use z-index variables or stacks).

#### Performance, Motion & Accessibility
*   Do not remove focus outline indicator rings without providing a
    `:focus-visible` alternative.
*   Do not mark a focusable interactive element as `aria-hidden="true"`.
*   Do not use raw standard `motion.*` elements (use lazy `m.*` elements).

### 9.2 What to Implement (Always Do)

#### TypeScript & React
*   Enforce named exports, type-only declarations (`import type`), and
    interfaces for component props.
*   Destructure props in the same order as defined in their interface.
*   Declare hooks, refs, and state in the order they render in the JSX tree.

#### Styling & CSS
*   Separate styles into co-located CSS modules.
*   Standardize class names in SCSS modules using kebab-case and a `.container`
    root selector.
*   Consume design values exclusively from tokens.

#### Performance, Motion & Accessibility
*   Wrap motion-bearing SCSS transitions in `@include prefers-motion`.
*   Give icon-only interactive controls an `aria-label` and mark inner icons
    as `aria-hidden="true"`.

#### Documentation & Workflow
*   Keep documentation and markdown files within a maximum limit of 80
    characters per line.
*   Write corresponding unit tests (`*.test.tsx` or `*.test.ts`) for any added
    logic.
*   Run linting suites (`pnpm lint` or equivalent), tests (`pnpm test`), and
    test builds (`pnpm build`) before pushing.

### 9.3 Self-Maintenance & PR Reviews
*   **Flag Discrepancies**: Reviewers (human or agent) must flag any code changes
    that violate these conventions.
*   **Instruction Synchronization**: If a change introduces a new architectural
    standard or styling pattern, the PR must include corresponding updates to
    this conventions file (or local overrides) to keep developer and agent
    instructions in sync.
