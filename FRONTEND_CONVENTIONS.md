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
    orchestrations.  Add clear annotations to public-facing functions so
    callers immediately understand the inputs, outputs, and failure cases.

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

### 2.3 Tight Modules and Concise Functions
Break large files into small, focused modules. Both modules and individual
functions should remain tight, concise, and do exactly one thing. This directly
maximizes code reuse, simplifies unit testing, and reduces cognitive load.

---

## 3. TypeScript & React Conventions

*   **Named Exports Only**: Never use `export default` for components or
    utilities, except where required by frameworks (like Next.js pages/layouts
    in `src/app/**` or config files).
*   **`interface` over `type`**: Always use `interface` for object shapes and
    component props (named `ComponentNameProps`, e.g., `interface CardProps`).
    Use `type` only for unions, tuples, mapping types, or function types. This
    ensures compatibility with Biome linting rules.
*   **Component Return Styles**: Prefer an explicit `return` block for React
    components. However, implicit arrow returns are permitted for stateless,
    simple, or single-line components (such as SVG icon wrappers).
*   **No `any` Types**: Never use `any`. Use `unknown` and type narrowing. If
    you must use `any` as an escape hatch, suppress only that specific line with
    a comment.
*   **Strict Comparison**: Use `===` and `!==` only. Avoid loose comparisons.
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

## 4. Styling Conventions

### 4.1 Unified Stack Recommendation
Whenever starting a new frontend app, align on a single styling stack (either
SCSS Modules or Tailwind CSS). Avoid mixing them within the same project to
prevent cognitive load, bundle inflation, and styling duplication. Shared
design tokens must remain the single source of truth.

### 4.2 SCSS Modules

*   **Setup**: Use CSS modules (`*.module.scss`), imported as `import s from
    './x.module.scss'`. Access multi-word classes via bracket notation (e.g.,
    `s['card-title']`).
*   **Root Selector**: The root class of every stylesheet module must always be
    `.container`. Single-component identity is derived from the component file
    namespace, not a unique class name.
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
    `.container[data-is-loading="true"]`).
*   **Design Tokens & Themes**: Standardize layout and palette values using
    tokens (e.g., from `@package/tokens` or project-specific theme
    definitions).
    *   **Colors**: Use semantic token names (e.g., `rgb(var(--color-primary))`,
        `rgb(var(--theme-background) / alpha%)`) to support branding and runtime
        themes. Avoid hardcoding raw hex values.
    *   **Z-Index**: Use z-index variables or stacks (`$z-index-*`) rather than
        arbitrary raw numeric values to avoid layering conflicts.

### 4.3 Tailwind CSS

*   **Standard Utilities Only**: Restrict styling to standard Tailwind classes
    (e.g., `w-px`, `mt-0.5`).
*   **Limit Arbitrary Values**: Avoid brackets notation (e.g., `h-[3px]`) unless
    representing a strict, non-standard layout dimension.
*   **Theme Integration**: Do not write arbitrary hex values inline. Add any
    reusable project colors, fonts, or assets to the Tailwind theme config.

---

## 5. Performance & Motion

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

---

## 6. Accessibility (a11y)

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

---

## 7. Security & Input Sanitization

*   **URL Parameter Validation**: Any input ingested from URL hashes, search
    parameters, or redirects (`window.location.hash`, `window.location.search`)
    is untrusted.
*   **Sanitization**: Sanitize query values before passing them to internal
    hooks, HTML renderers, or navigation logic.
*   **Prevent Injection**: Never insert raw or unescaped parameter values
    directly into DOM-rendering blocks to guard against Cross-Site Scripting
    (XSS) and Open Redirect vulnerabilities.

---

## 8. Development Workflow Checklists

### 8.1 What to Avoid (Never Do)
*   Do not use `any` type (suppress single line with a comment if truly
    unavoidable).
*   Do not use default exports, except in route mappings/configs.
*   Do not use relative parent directory imports (`../`). Use path aliases
    (`~/`).
*   Do not hardcode pixel sizes or hex colors (use token variables).
*   Do not add custom styled wrappers inside layout loops (keep resets clean).

### 8.2 What to Implement (Always Do)
*   Enforce named exports, type-only declarations (import type), and
    interfaces for props.
*   Write corresponding unit tests (`*.test.tsx` or `*.test.ts`) for any added
    logic.
*   Keep documentation and markdown files within a maximum limit of 80
    characters per line (code files are managed by formatters).
*   Separate styles into co-located modules.
*   Run linting suites (`pnpm lint`), tests (`pnpm test`), and test builds
    (`pnpm build`) before pushing.
*   Add screen-reader titles for icon-only interactions.

### 8.3 Self-Maintenance & PR Reviews
*   **Flag Discrepancies**: Reviewers (human or agent) must flag any code changes
    that violate these conventions.
*   **Instruction Synchronization**: If a change introduces a new architectural
    standard or styling pattern, the PR must include corresponding updates to
    this conventions file (or local overrides) to keep developer and agent
    instructions in sync.
