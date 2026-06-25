# PR 363 Review Comments & Fixes Tracking

This document tracks the code review feedback received on [PR 363](https://github.com/datacommonsorg/tools/pull/363) and the progress of the corresponding fixes.

## Global / Architectural Feedback

- [x] **File Renaming**: Rename files in the project to adhere to the frontend style guide:
  - Use `snake_case` for filenames.
  - Use category-first naming (e.g., prefixing components with their subfolder/domain names where appropriate, or grouping them cleanly).
  - *Status: Completed (Renamed all files and updated component identifiers and import statements)*
- [x] **Inline Styling Extraction** [Can leave for followup PR]:
  - Extract inline styling in React components (under `components/`) into style constants or clean CSS classes, or place styling-related constants in a template/theme file.
  - *Status: Completed (Added TODO comments in code files for followup)*

## Inline Review Comments

### File: `narratives/src/api/dcObservations.ts`

- [x] **Comment #1 (discussion_r3455855023)**:
  - **Location**: Lines 1-3 (File header description comment).
  - **Feedback**: Use `/** ... */` style multiline comments instead of `//` double-slash comments for all file descriptions.
  - **Status**: Completed
- [x] **Comment #2 (discussion_r3455868024)**:
  - **Location**: Line 5 (Definitions of type aliases).
  - **Feedback**: Per Google TypeScript style guide, prefer `interface` over `type` for `SeriesPoint`, `SeriesResponse`, and `PointResponse`.
  - **Status**: Completed
- [x] **Comment #3 (discussion_r3455917165)**:
  - **Location**: Lines 34-64 (`buildSeriesUrl` and helper parameters).
  - **Feedback**: Use more descriptive variable names than `u`, `v`, and `e` (e.g. `u` -> `url`, `v` -> `variableDcid`, `e` -> `entityDcid`). Avoid overloading `e` as it is typically used for error/event.
  - **Status**: Completed
- [x] **Comment #4 (discussion_r3456144443)**:
  - **Location**: Lines 91-94 (Function description comments).
  - **Feedback**: Convert function documentation `//` comments to `/** ... */` JSDoc comments.
  - **Status**: Completed
- [x] **Comment #5 (discussion_r3456146137)**:
  - **Location**: Lines 63-66 (`fetchSeries` and `fetchPoint`).
  - **Feedback**: Add a JSDoc comment to `fetchSeries()` and `fetchPoint()` and all exported functions.
  - **Status**: Completed

### File: `narratives/src/components/CitationChip.tsx`

- [x] **Comment #6 (discussion_r3463904433)**:
  - **Location**: Lines 58-60 (Helper comment).
  - **Feedback**: Convert comments describing functions/helpers to JSDoc format docstrings.
  - **Status**: Completed

### File: `narratives/src/components/ChartTile.tsx`

- [x] **Comment #7 (discussion_r3463907668)**:
  - **Location**: Lines 61-64 (`ChartTile` component).
  - **Feedback**: Add fileoverview JSDoc block, add component JSDoc docstring, and use named exports (`export function ChartTile(...)`) instead of `export default`.
  - **Status**: Completed
- [x] **Comment #8 (discussion_r3464007995)** [Can leave for followup PR]:
  - **Location**: Lines 234-237 (Recharts renderers section).
  - **Feedback**: Splitting this very big file into multiple files under a `charts/` subfolder (e.g., `chart_tile.tsx`, `chart_card.tsx`, `chart_graph.tsx`, etc.).
  - **Status**: Completed (Added TODO comment to code as permitted for followup).

### File: `narratives/src/components/AnswerPanel.tsx`

- [x] **Comment #9 (discussion_r3464012810)**:
  - **Location**: Lines 36-39 (`AnswerPanel` component).
  - **Feedback**: Add fileoverview JSDoc, component JSDoc docstring, and use named exports (`export function AnswerPanel(...)`) instead of `export default`.
  - **Status**: Completed
- [x] **Comment #10 (discussion_r3464019352)**:
  - **Location**: Lines 129-131 (Export PDF pill comment).
  - **Feedback**: Convert double-slash comment to JSDoc format docstring.
  - **Status**: Completed
