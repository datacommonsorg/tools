# Atlas card placement

How cards get their position on the tldraw canvas, and how the camera follows
them. Everything described here lives in
[`register_card_placement.ts`](register_card_placement.ts)
(`registerCardPlacement`), configured by
`CARD_GRID` in [`config.ts`](config.ts), and wired up once in
[`atlas_provider.tsx`](atlas_provider.tsx)'s `onMount`.

## The model: cards flow like text

Placement is a **cursor**, not a spatial search. Only the last few cards and
the canvas's outer extents matter:

- Each new card lands against the **previous card's right edge + gutter**, on
  the same row top — unless another card already occupies that slot, in which
  case the card wraps instead. This is the one collision check placement
  makes, and it covers only the row in progress.
- A row holds at most the breakpoint's **column count**: 1 below the tablet
  breakpoint, 2 below laptop, 3 above (`CARD_GRID`, which
  also sets the per-breakpoint gutter). Breakpoints match against the
  **browser window in screen px** — never the zoomed page — so zoom can't
  change how many cards stack.
- When the row is full or the next slot is blocked, the card **wraps** below
  both the **tracked row** and the **lowest card on the canvas**, whichever
  sits lower. Both terms are needed: the tracked row can be stale (see
  *Rooting*), and the canvas cannot see cards created earlier in the same
  atomic operation, since tldraw publishes them only once the whole operation
  commits. Uneven card heights never stagger the grid.
- A card that **opens a batch** always starts a row of its own, so a set of
  cards arriving together lands on one line instead of splitting across an
  older row's leftover slots.
- Cards always use their `CARD_VARIANT_SIZE_DEFAULT` width — never capped
  to the breakpoint's column width, so a full row may run wider than the
  viewport at low column counts.

The cursor tracks the current row (ids + footprints), the row's start x, and
`gridIds` — every card placed since the grid was last rooted. Row bounds are
re-read from the store at each placement, so resizes and auto-height shrinks
are respected; entries not yet committed (multi-card paste siblings, which
place before the batch commits) keep their placement bounds.

## Where a new row starts horizontally

A wrap within a batch keeps the grid's current x. A card that opens a batch
picks its x from what the caller knows about the batch:

- **Size known** (`rowStart: 'batch'`) — the query flow registers a result's
  cards in one store update, so `sync_store` passes every width and the row is
  centered under the canvas's content using the width it will really occupy.
- **Size unknown** (`rowStart: 'align'`) — clones are created one at a time,
  before their siblings exist, so a paste keeps the grid's x.

The row width is never assumed. An assumed width biases every row toward the
side the estimate overshoots, and because each biased row widens the content
that the next row is centered against, successive batches walk further out.


## Rooting and re-rooting

- **Empty canvas** → the grid roots at the viewport's top-left.
- **User moves a card** → the grid re-roots there: the moved card becomes the
  sole member of the cursor's row, so later rows wrap back to its x and the
  next card lands beside it — unless that card opens a batch, which always
  starts a row of its own. A "move" is any user change
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
cards, with the first clone of the operation opening the row. Two exceptions
/ gotchas:

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
2. If the frame fits without zooming out past `MIN_ZOOM` → zoom to it. The
   frame is the whole **canvas** when the card opened a new row, so the row is
   seen in the context of everything already there; otherwise it is the
   **grid being built** (the cursor's `gridIds`), which may exclude older
   clusters far away.
3. Otherwise → pan to center the new card.

On the single-column (mobile) breakpoint step 2 is skipped: the canvas is
treated as a vertical scrolling feed, so the camera always pans down to the
new card instead of zooming out to fit the stack. And when several cards
arrive in one batch (a multi-card query, a multi-card paste), only the
**first** of the set is revealed — the camera pans to it and stays, rather
than chasing each card to the bottom of the stack.

> [!NOTE]
> Step 2 reads a flag set by the last `place()` call. tldraw runs every
> `beforeCreate` of an atomic operation before any `afterCreate`, so during a
> multi-card paste the flag describes the last card placed rather than the one
> being revealed. Cards from the `add` flow are unaffected — each completes
> its place-then-create before the next begins.

## Known trade-offs (deliberate)

- **Collision checks are limited to the next slot in the row.** Deleting a
  card leaves a hole (no gap-filling), and a new row clears the canvas floor
  rather than searching for free space, so a card parked far below pushes
  later rows below it. Chosen for predictability.
- **Auto-height timing**: cards are created at their variant's max height and
  shrink to content after first paint (`useCardAutoHeight`). Placements that
  happen before the shrink (e.g. several cards streaming in from one query)
  space rows by the reserved heights, leaving larger vertical gaps than
  placements made after paint. Accepted for now.

