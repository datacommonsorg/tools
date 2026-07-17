# Atlas card placement

How cards get their position on the tldraw canvas, and how the camera follows
them. Everything described here lives in
[`register_card_placement.ts`](register_card_placement.ts)
(`registerCardPlacement` + `fitCardSize`), configured by
`CARD_GRID` in [`config.ts`](config.ts), and wired up once in
[`atlas_provider.tsx`](atlas_provider.tsx)'s `onMount`.

## The model: cards flow like text

Placement is a **cursor**, not a spatial search. There are no collision
checks and no dependence on the camera — only the last few cards matter:

- Each new card lands against the **previous card's right edge + gutter**, on
  the same row top.
- A row holds at most the breakpoint's **column count**: 1 below the tablet
  breakpoint, 2 below laptop, 3 above (`CARD_GRID`, which
  also sets the per-breakpoint gutter). Breakpoints match against the
  **browser window in screen px** — never the zoomed page — so zoom can't
  change how many cards stack.
- When the row is full, the next card **wraps**: back to the row's start x,
  just below the **tallest** card of the row above. Uneven card heights never
  stagger the grid.
- Card widths are capped per breakpoint by `fitCardSize` (window width ÷
  columns, zoom-independent, never below `CARD_SIZE_MIN`), so the column
  count actually fits side by side at 1:1 zoom. The `CARD_VARIANT_SIZE_DEFAULT`
  widths act as maximums.

The cursor tracks the current row (ids + footprints), the row's start x, and
`gridIds` — every card placed since the grid was last rooted. Row bounds are
re-read from the store at each placement, so resizes and auto-height shrinks
are respected; entries not yet committed (multi-card paste siblings, which
place before the batch commits) keep their placement bounds.

## Rooting and re-rooting

- **Empty canvas** → the grid roots at the viewport's top-left.
- **User moves a card** → the grid re-roots there: the moved card becomes the
  sole member of the cursor's row, so the next card (new or pasted) lands
  beside it and later rows wrap back to its x. A "move" is any user change
  that shifts x/y while leaving w/h alone — drags, arrow-key nudges, align —
  detected structurally in an `afterChange` handler rather than via tool
  state (tool-state gating proved unreliable). Resizes change w/h together
  with x/y and do not re-root. Multi-card move → the last card reported wins.
  Note: undoing a move also re-roots (it's an x/y-only user change).
- **No tracked cursor but cards exist** (fresh mount over a populated canvas,
  or the tracked row was fully deleted) → a cursor is derived from geometry:
  the bottom-most-then-right-most card counts as last placed, and the cards
  sharing its row top form the current row.
- **Deleted cards** are pruned from the cursor; deleting the whole tracked
  row drops the cursor so the next placement re-derives.

## Clones (copy / paste / duplicate)

Cards created outside the `add` flow (detected by `meta.originId` differing
from the shape's own id) are positioned onto the grid in a
`beforeCreate` handler — pastes and duplicates follow the same flow as new
cards. Two exceptions / gotchas:

- **Alt-drag duplicates** are created mid-drag with the pointer deciding
  where they go; they're left alone, and the move tracker re-roots the grid
  to them as they're dragged.
- **tldraw's paste re-centering is vetoed.** tldraw's
  `putContentOntoCurrentPage` checks, *after* creating pasted shapes, whether
  any of them overlaps the viewport — if none do, it translates them all to
  the viewport's center. Since placement often puts a paste on a row outside
  the current view, that would tear cards off the grid. Cards placed within
  the current synchronous task are therefore immune to position changes (a
  `beforeChange` veto backed by a microtask-scoped set); the camera goes to
  the card instead of the card to the camera. Side effect: "paste at cursor"
  (context-menu paste) is also overridden — pastes always join the grid.

## Camera (`keepInView`)

After every card creation, in order:

1. Card already fully in the viewport → leave the camera alone.
2. If the whole **grid being built** (the cursor's `gridIds` — not the entire
   canvas, which may span older clusters far away) fits without zooming out
   past `MIN_ZOOM` → zoom to frame it.
3. Otherwise → pan to center the new card.

On the single-column (mobile) breakpoint step 2 is skipped: the canvas is
treated as a vertical scrolling feed, so the camera always pans down to the
new card instead of zooming out to fit the stack. And when several cards
arrive in one batch (a multi-card query, a multi-card paste), only the
**first** of the set is revealed — the camera pans to it and stays, rather
than chasing each card to the bottom of the stack.

## Known trade-offs (deliberate)

- **No collision checks**: deleting a card leaves a hole (no gap-filling),
  and a growing grid can run over cards parked in its path long ago. Chosen
  for predictability.
- **Auto-height timing**: cards are created at their variant's max height and
  shrink to content after first paint (`useCardAutoHeight`). Placements that
  happen before the shrink (e.g. several cards streaming in from one query)
  space rows by the reserved heights, leaving larger vertical gaps than
  placements made after paint. Accepted for now.
