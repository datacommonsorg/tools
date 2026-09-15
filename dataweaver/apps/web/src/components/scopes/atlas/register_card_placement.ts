/**
 * Card placement: where cards land on the canvas and how the camera follows
 * them. See `PLACEMENT.md` for the full model and its trade-offs.
 */

import {
  Box,
  type Editor,
  type TLCreateShapePartial,
  type TLShape,
  type TLShapeId,
} from 'tldraw';
import { CARD_GRID, KEEP_IN_VIEW_ANIMATION, MIN_ZOOM } from './config';
import type { CardBounds, CardPosition, CardShape, CardSize } from './helpers';

/**
 * The grid for the current window width: cards per row and the gutter
 * between them. Screen px, never the zoomed page — layout tracks the device,
 * not the camera.
 */
export const resolveGrid = (editor: Editor) => {
  const screenWidth = editor.getViewportScreenBounds().width;

  const breakpoint =
    screenWidth >= CARD_GRID.laptop.breakpoint
      ? CARD_GRID.laptop
      : screenWidth >= CARD_GRID.tablet.breakpoint
        ? CARD_GRID.tablet
        : CARD_GRID.mobile;

  return {
    columns: breakpoint.columns,
    gutter: breakpoint.gutter,
    screenWidth,
  };
};

/** A card the cursor tracks: its shape ID plus its footprint at placement. */
interface CursorEntry {
  id: TLShapeId;
  bounds: CardBounds;
}

/**
 * Where the next card goes: the current row in placement order, the X rows
 * wrap back to, and `gridIds` — every card placed since the grid was last
 * rooted (only used by `keepInView` to frame the grid, not placement).
 */
interface GridCursor {
  row: CursorEntry[];
  rowStartX: number;
  gridIds: TLShapeId[];
}

/** Convert a shape's position and size into `CardBounds`. */
const mapShapeToBounds = (
  shape: Pick<CardShape, 'x' | 'y' | 'props'>,
): CardBounds => {
  return { x: shape.x, y: shape.y, w: shape.props.w, h: shape.props.h };
};

/**
 * The cursor with each tracked bounds re-read from the store, so resizes and
 * auto-height shrinks are respected. Entries not committed yet (multi-card
 * paste siblings) keep their placement bounds.
 */
const refreshCursor = (editor: Editor, cursor: GridCursor): GridCursor => {
  const row = cursor.row.map((entry) => {
    const shape = editor.getShape(entry.id);
    if (!shape || shape.type !== 'card') return entry;

    return { ...entry, bounds: mapShapeToBounds(shape) };
  });

  return { ...cursor, row };
};

/**
 * Rebuild the cursor from the canvas when none is tracked (fresh mount over
 * existing cards): the bottom-most-then-right-most card counts as last
 * placed, and the cards sharing its row top form the current row.
 */
const deriveCursor = (
  shapes: ReturnType<Editor['getCurrentPageShapes']>,
  columns: number,
): GridCursor | null => {
  const entries: CursorEntry[] = [];

  for (const shape of shapes) {
    if (shape.type !== 'card') continue;

    entries.push({ id: shape.id, bounds: mapShapeToBounds(shape) });
  }

  // Ignore if there are no cards on the canvas
  const [first] = entries;
  if (!first) return null;

  // Find the bottom-most-then-right-most card, which counts as last placed
  let last = first;
  for (const entry of entries) {
    if (
      entry.bounds.y > last.bounds.y ||
      (entry.bounds.y === last.bounds.y && entry.bounds.x > last.bounds.x)
    ) {
      last = entry;
    }
  }

  // Find the row of cards sharing that card's top, sorted left to right and
  // capped to the grid's column count (the rest wrap to the next row)
  const row = entries
    .filter((entry) => Math.abs(entry.bounds.y - last.bounds.y) < 1)
    .sort((a, b) => a.bounds.x - b.bounds.x)
    .slice(-columns);

  // If the row is empty, something went wrong - ignore
  const [rowStart] = row;
  if (!rowStart) return null;

  return {
    row,
    rowStartX: rowStart.bounds.x,
    gridIds: row.map((entry) => entry.id),
  };
};

interface NextSlotResult {
  position: CardPosition;
  cursor: GridCursor;
}

/**
 * How a card that opens its own row picks that row's x.
 *
 * - `batch` — every card arriving together is known, so the row is centered
 *   on the canvas's content using the width it will really occupy. Both the
 *   query flow and clones (see `trackCreateBatch`) report their batch.
 * - `align` — the batch is unknown, so the row keeps the grid's current x.
 *   Assuming a width instead would bias every row toward the side the
 *   estimate overshoots, and each biased row widens the content the next row
 *   is measured against, so successive batches walk further out.
 */
export type RowStart = { kind: 'batch'; widths: number[] } | { kind: 'align' };

/**
 * Widths of the cards in a set of shapes about to be created, in the order
 * given. Cards whose width is left to the schema's default are skipped — the
 * row can only be measured from widths that are actually stated.
 */
const cardWidths = (
  shapes: readonly { type: string; props?: { w?: number } }[],
): number[] => {
  const widths: number[] = [];

  for (const shape of shapes) {
    const width = shape.type === 'card' ? shape.props?.w : undefined;
    if (width !== undefined) widths.push(width);
  }

  return widths;
};

/** Card extents across the whole canvas. */
interface CanvasCardMetrics {
  /** Bottom edge of the lowest card. */
  floor: number;
  /** Left edge of the leftmost card. */
  minX: number;
  /** Right edge of the rightmost card. */
  maxX: number;
}

/**
 * Extents of every card on the canvas, or null with no cards. One pass: a new
 * row needs the floor to clear existing cards, and a centered row needs the
 * horizontal span to center under.
 *
 * Reads the store, so it only sees committed cards. Cards placed earlier in
 * the same atomic operation — the siblings of a multi-card paste — are absent,
 * which is why the floor below is combined with the cursor's tracked row.
 */
const canvasCardMetrics = (
  shapes: ReturnType<Editor['getCurrentPageShapes']>,
): CanvasCardMetrics | null => {
  let metrics: CanvasCardMetrics | null = null;

  for (const shape of shapes) {
    if (shape.type !== 'card') {
      continue;
    }

    const bottom = shape.y + shape.props.h;
    const right = shape.x + shape.props.w;

    if (!metrics) {
      metrics = { floor: bottom, minX: shape.x, maxX: right };
      continue;
    }

    metrics.floor = Math.max(metrics.floor, bottom);
    metrics.minX = Math.min(metrics.minX, shape.x);
    metrics.maxX = Math.max(metrics.maxX, right);
  }

  return metrics;
};

/** Whether two card-sized rectangles overlap at all. */
const boundsOverlap = (a: CardBounds, b: CardBounds): boolean => {
  return (
    a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
  );
};

/**
 * Width the first row of `widths` will occupy: the cards that fit within the
 * column count, plus the gutters between them. Cards beyond it wrap onto the
 * next row and add nothing here.
 */
const batchRowWidth = (
  widths: number[],
  columns: number,
  gutter: number,
): number => {
  const row = widths.slice(0, columns);
  const cards = row.reduce((total, width) => total + width, 0);
  return cards + Math.max(row.length - 1, 0) * gutter;
};

/**
 * Report the set of cards each creation is about to make, for as long as that
 * creation runs. Clones are positioned in a `beforeCreate` handler, which
 * tldraw hands one record at a time, so the first clone of a paste cannot see
 * its siblings. Every creation in tldraw — new card, paste, drop, duplicate —
 * funnels through `createShapes` with the whole set in one array, so this is
 * the one place the set is knowable before any of it exists.
 *
 * Returns a function restoring the editor's own method.
 */
const trackCreateBatch = (
  editor: Editor,
  report: (widths: number[] | null) => void,
): (() => void) => {
  const createShapes = editor.createShapes;

  editor.createShapes = <TShape extends TLShape>(
    shapes: TLCreateShapePartial<TShape>[],
  ) => {
    report(cardWidths(shapes));
    try {
      return createShapes.call(editor, shapes);
    } finally {
      report(null);
    }
  };

  return () => {
    editor.createShapes = createShapes;
  };
};

/** Calculate position for a card about to be created + its updated cursor. */
const nextSlot = (
  editor: Editor,
  id: TLShapeId,
  size: CardSize,
  cursor: GridCursor | null,
  rowStart: RowStart | null,
): NextSlotResult => {
  const { columns, gutter } = resolveGrid(editor);

  let pageShapes: ReturnType<Editor['getCurrentPageShapes']> | null = null;
  const getPageShapes = () => {
    if (!pageShapes) {
      pageShapes = editor.getCurrentPageShapes();
    }
    return pageShapes;
  };

  const latestCursor = cursor
    ? refreshCursor(editor, cursor)
    : deriveCursor(getPageShapes(), columns);

  const entry = (position: CardPosition): CursorEntry => {
    return { id, bounds: { ...position, ...size } };
  };

  const rowFirst = latestCursor ? latestCursor.row[0] : null;
  const rowLast = latestCursor
    ? latestCursor.row[latestCursor.row.length - 1]
    : null;

  // Empty canvas: return the first slot in the top-left corner of viewport
  if (!latestCursor || !rowFirst || !rowLast) {
    const viewport = editor.getViewportPageBounds();
    const position = {
      x: viewport.minX + gutter,
      y: viewport.minY + gutter,
    };
    return {
      position,
      cursor: { row: [entry(position)], rowStartX: position.x, gridIds: [id] },
    };
  }

  // Room in the row: place against the previous card's right edge — unless a
  // stray card blocks the gap, or this card opens a row of its own. Either
  // case falls through below.
  if (!rowStart && latestCursor.row.length < columns) {
    const previousBounds = rowLast.bounds;
    const position = {
      x: previousBounds.x + previousBounds.w + gutter,
      y: rowFirst.bounds.y,
    };

    // Only this row's own cards are expected in the slot; anything else
    // sitting there — including a card the grid placed on an earlier row —
    // is a collision
    const rowIds = new Set(latestCursor.row.map((rowEntry) => rowEntry.id));
    const candidate: CardBounds = { ...position, ...size };
    const blocked = getPageShapes().some((shape) => {
      if (shape.type !== 'card' || rowIds.has(shape.id)) {
        return false;
      }
      return boundsOverlap(candidate, mapShapeToBounds(shape));
    });

    if (!blocked) {
      return {
        position,
        cursor: {
          ...latestCursor,
          row: [...latestCursor.row, entry(position)],
          gridIds: [...latestCursor.gridIds, id],
        },
      };
    }
  }

  const metrics = canvasCardMetrics(getPageShapes());

  // Row full, blocked, or opening a row: drop below both the tracked row and
  // the lowest card on the canvas. Neither alone is enough — the tracked row
  // can be stale (re-rooted on a card the user dragged, which may sit above
  // others), and the canvas misses the siblings of an in-flight paste, which
  // are not in the store until the whole operation commits.
  const trackedRowBottom = Math.max(
    ...latestCursor.row.map(({ bounds }) => bounds.y + bounds.h),
  );
  const floor = Math.max(trackedRowBottom, metrics?.floor ?? trackedRowBottom);

  // A batch of known size centers its row under the canvas's content;
  // anything else keeps the grid's x, since the row's width isn't knowable
  // yet and a guess would drift (see `RowStart`)
  let rowStartX = latestCursor.rowStartX;
  if (rowStart?.kind === 'batch' && metrics) {
    const rowWidth = batchRowWidth(rowStart.widths, columns, gutter);
    rowStartX = (metrics.minX + metrics.maxX) / 2 - rowWidth / 2;
  }

  const position = {
    x: rowStartX,
    y: floor + gutter,
  };
  return {
    position,
    cursor: {
      row: [entry(position)],
      rowStartX,
      gridIds: [...latestCursor.gridIds, id],
    },
  };
};

/** Whether `bounds` can fit fully on screen without zooming past `MIN_ZOOM`. */
export const canFitWithinZoomCap = (
  editor: Editor,
  bounds: Box,
  gutter: number,
): boolean => {
  // Degenerate bounds would divide to Infinity below and wrongly report a fit
  if (bounds.w <= 0 || bounds.h <= 0) return false;

  const screenBounds = editor.getViewportScreenBounds();
  const fitZoom = Math.min(
    (screenBounds.width - gutter) / bounds.w,
    (screenBounds.height - gutter) / bounds.h,
  );
  return fitZoom >= MIN_ZOOM;
};

/**
 * Bounds enclosing the cursor's grid (plus `bounds`, the card just placed).
 * Null without a cursor — the caller falls back to the whole canvas.
 */
const gridBounds = (
  editor: Editor,
  cursor: GridCursor | null,
  bounds: CardBounds,
): Box | null => {
  if (!cursor) return null;

  let minX = bounds.x;
  let minY = bounds.y;
  let maxX = bounds.x + bounds.w;
  let maxY = bounds.y + bounds.h;

  for (const id of cursor.gridIds) {
    const shape = editor.getShape(id);
    if (!shape || shape.type !== 'card') continue;

    minX = Math.min(minX, shape.x);
    minY = Math.min(minY, shape.y);
    maxX = Math.max(maxX, shape.x + shape.props.w);
    maxY = Math.max(maxY, shape.y + shape.props.h);
  }

  return new Box(minX, minY, maxX - minX, maxY - minY);
};

/**
 * Reveal a freshly placed card:
 * 1. Fully in the viewport already → leave the camera be.
 * 2. Grid fits within the zoom cap → zoom out to frame it.
 * 3. Otherwise → pan to the new card.
 * Single column (mobile) skips step 2 — the stack reads as a scrolling feed,
 * so the camera pans instead of zooming out.
 * A batch that started a new row frames the whole canvas instead of just its
 * own grid, so the new row is seen in the context of everything already there.
 */
const keepInView = (
  editor: Editor,
  bounds: CardBounds,
  cursor: GridCursor | null,
  frameWholeCanvas: boolean,
): void => {
  const viewport = editor.getViewportPageBounds();

  const fullyVisible =
    bounds.x >= viewport.minX &&
    bounds.y >= viewport.minY &&
    bounds.x + bounds.w <= viewport.maxX &&
    bounds.y + bounds.h <= viewport.maxY;

  // Already fully on screen — don't move the camera at all
  if (fullyVisible) return;

  const { columns, gutter } = resolveGrid(editor);

  // If we can fit the grid within the zoom cap - zoom to fit
  if (columns > 1) {
    const frame = frameWholeCanvas
      ? editor.getCurrentPageBounds()
      : (gridBounds(editor, cursor, bounds) ?? editor.getCurrentPageBounds());
    if (frame && canFitWithinZoomCap(editor, frame, gutter)) {
      editor.zoomToBounds(frame, {
        inset: gutter,
        animation: KEEP_IN_VIEW_ANIMATION,
      });
      return;
    }
  }

  // Single column, or the grid would blow past the zoom cap — pan to the card
  editor.centerOnPoint(
    { x: bounds.x + bounds.w / 2, y: bounds.y + bounds.h / 2 },
    { animation: KEEP_IN_VIEW_ANIMATION },
  );
};

export interface CardPlacement {
  /**
   * Get the position for a card about to be created and advance the cursor.
   *
   * Pass `rowStart` when this card opens a row of its own: `batch` when every
   * card arriving with it is known now (its row is centered on the canvas's
   * content), `align` when they are not (its row keeps the grid's x). Omit it
   * for a card that should flow into the row in progress.
   */
  place(
    id: TLShapeId,
    size: CardSize,
    rowStart?: RowStart | null,
  ): CardPosition;

  /** Unregister every placement side effect and drop tracked state. */
  cleanup(): void;
}

/**
 * The card placement system: owns the grid cursor and registers the side
 * effects that keep it honest — positioning clones, vetoing tldraw's paste
 * re-centering, re-rooting the grid at cards the user moves, revealing
 * created cards, and pruning deleted ones.
 */
export const registerCardPlacement = (editor: Editor): CardPlacement => {
  let cursor: GridCursor | null = null;

  // Whether the most recent `place()` call opened a new row, read by
  // `cleanupRevealCreated` to decide how to frame the camera.
  //
  // Caveat: tldraw runs every `beforeCreate` of an atomic operation before
  // any `afterCreate`, so during a multi-card paste this reports the last
  // card placed rather than the card being revealed. Cards added through
  // `place`-then-`createShape` (the query flow) are unaffected — each one
  // completes before the next begins.
  let lastPlacementStartedNewRow = false;

  const place = (
    id: TLShapeId,
    size: CardSize,
    rowStart: RowStart | null = null,
  ): CardPosition => {
    const slot = nextSlot(editor, id, size, cursor, rowStart);
    cursor = slot.cursor;
    lastPlacementStartedNewRow = rowStart !== null;
    return slot.position;
  };

  // Cards pasted within the current task. tldraw's paste re-centers shapes
  // that land fully off-screen right after creating them, which would tear
  // a card off the grid — the veto below blocks that. A paste is fully
  // synchronous and has no 'finished' hook, so a queued microtask expires
  // each guard exactly when the operation ends
  const pastedThisTask = new Set<TLShapeId>();

  // The widths of the card set being created, for the row its first clone
  // opens. Set only while the creation that reported it runs
  let cloneBatchWidths: number[] | null = null;
  const cleanupTrackCreateBatch = trackCreateBatch(editor, (widths) => {
    cloneBatchWidths = widths;
  });

  // Clones (copy/paste, duplicate) flow onto the grid as they're created —
  // except alt-drag duplicates, which the user's pointer is placing
  const cleanupPlaceClones = editor.sideEffects.registerBeforeCreateHandler(
    'shape',
    (shape) => {
      const originId = shape.meta.originId;
      if (
        // Ignore non-card shapes
        shape.type !== 'card' ||
        // Or if the shape is its own origin (new card, not a clone)
        originId === shape.id ||
        // Or if the user is actively dragging something in canvas
        editor.isIn('select.translating')
      ) {
        return shape;
      }

      // The first clone of the operation opens a row for the whole batch and
      // its siblings fill that row. Anything creating clones outside the
      // tracked entry points leaves the row aligned to the grid instead
      const isFirstClone = pastedThisTask.size === 0;
      const rowStart: RowStart | null = !isFirstClone
        ? null
        : cloneBatchWidths?.length
          ? { kind: 'batch', widths: cloneBatchWidths }
          : { kind: 'align' };

      pastedThisTask.add(shape.id);
      queueMicrotask(() => pastedThisTask.delete(shape.id));

      return {
        ...shape,
        ...place(shape.id, { w: shape.props.w, h: shape.props.h }, rowStart),
      };
    },
  );

  // Veto tldraw's re-centering of pastes that land off-screen: placement is
  // authoritative, the camera goes to the card rather than the card to it
  const cleanupKeepPlacement = editor.sideEffects.registerBeforeChangeHandler(
    'shape',
    (previous, next) => {
      if (
        // Ignore non-card shapes
        next.type !== 'card' ||
        // Or cards that weren't pasted within the current task
        !pastedThisTask.has(next.id) ||
        // Or changes that don't touch the card's position
        (previous.x === next.x && previous.y === next.y)
      ) {
        return next;
      }

      return { ...next, x: previous.x, y: previous.y };
    },
  );

  // When the user moves a card, re-root the grid there: the next card lands
  // beside it and rows wrap back to its x. A move shifts x/y but not w/h —
  // that separates drags and nudges from resizes, whatever the tool state.
  const cleanupTrackMoved = editor.sideEffects.registerAfterChangeHandler(
    'shape',
    (previous, next, source) => {
      if (
        // Ignore non-card shapes
        previous.type !== 'card' ||
        next.type !== 'card' ||
        // Or changes that didn't come from the local user
        source !== 'user' ||
        // Or changes that don't move the card
        (previous.x === next.x && previous.y === next.y) ||
        // Or resizes (a move shifts x/y but never w/h)
        previous.props.w !== next.props.w ||
        previous.props.h !== next.props.h
      ) {
        return;
      }

      cursor = {
        row: [{ id: next.id, bounds: mapShapeToBounds(next) }],
        rowStartX: next.x,
        gridIds: [next.id],
      };
    },
  );

  // Whether a reveal already ran this task. On single-column, a set of cards
  // arriving at once pans the camera to its first card only — not each one
  // in turn. The flag expires with the task's microtasks, so the next burst
  // reveals its own first card
  let revealedThisTask = false;

  // Whenever a card is created (new or clone), move the camera so it lands
  // in view within the context of its grid
  const cleanupRevealCreated = editor.sideEffects.registerAfterCreateHandler(
    'shape',
    (shape) => {
      // Ignore non-card shapes
      if (shape.type !== 'card') return;

      // On single-column, only the first card of a task's set is revealed
      if (resolveGrid(editor).columns === 1) {
        if (revealedThisTask) return;

        revealedThisTask = true;
        queueMicrotask(() => {
          revealedThisTask = false;
        });
      }

      keepInView(
        editor,
        mapShapeToBounds(shape),
        cursor,
        lastPlacementStartedNewRow,
      );
    },
  );

  // Deleted cards can't guide placement or framing: drop them from the
  // cursor, and drop the cursor itself once its row is empty (a fresh one
  // is then derived from whatever cards remain)
  const cleanupPruneDeleted = editor.sideEffects.registerAfterDeleteHandler(
    'shape',
    (shape) => {
      // Ignore non-card shapes, or deletes with no cursor to prune
      if (shape.type !== 'card' || !cursor) return;

      const row = cursor.row.filter((entry) => entry.id !== shape.id);
      const gridIds = cursor.gridIds.filter((id) => id !== shape.id);
      cursor = row.length > 0 ? { ...cursor, row, gridIds } : null;
    },
  );

  return {
    place,
    cleanup() {
      cleanupPlaceClones();
      cleanupKeepPlacement();
      cleanupTrackMoved();
      cleanupRevealCreated();
      cleanupPruneDeleted();
      cleanupTrackCreateBatch();
      cursor = null;
      pastedThisTask.clear();
    },
  };
};
