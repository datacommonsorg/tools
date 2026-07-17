/**
 * Card placement: where cards land on the canvas and how the camera follows
 * them. See `PLACEMENT.md` for the full model and its trade-offs.
 */

import { Box, type Editor, type TLShapeId } from 'tldraw';
import {
  CARD_GRID,
  CARD_SIZE_MIN,
  KEEP_IN_VIEW_ANIMATION,
  MIN_ZOOM,
} from './config';
import type { CardBounds, CardPosition, CardShape, CardSize } from './helpers';

/**
 * The grid for the current window width: cards per row and the gutter
 * between them. Screen px, never the zoomed page — layout tracks the device,
 * not the camera.
 */
const resolveGrid = (editor: Editor) => {
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

/**
 * Get given `size` capped to the grid's column width, so the card actually fits
 * within current screen width without needing to zoom out past the minimum.
 */
export const fitCardSize = (editor: Editor, size: CardSize): CardSize => {
  const { columns, gutter, screenWidth } = resolveGrid(editor);
  const maxWidth = (screenWidth - gutter * (columns + 1)) / columns;
  const cappedWidth = Math.max(CARD_SIZE_MIN.w, Math.min(size.w, maxWidth));
  return { w: cappedWidth, h: size.h };
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
const deriveCursor = (editor: Editor, columns: number): GridCursor | null => {
  const entries: CursorEntry[] = [];

  for (const shape of editor.getCurrentPageShapes()) {
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

/** Calculate position for a card about to be created + its updated cursor. */
const nextSlot = (
  editor: Editor,
  id: TLShapeId,
  size: CardSize,
  cursor: GridCursor | null,
): NextSlotResult => {
  const { columns, gutter } = resolveGrid(editor);
  const latestCursor = cursor
    ? refreshCursor(editor, cursor)
    : deriveCursor(editor, columns);

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

  // Room in the row: place against the previous card's right edge
  if (latestCursor.row.length < columns) {
    const previousBounds = rowLast.bounds;
    const position = {
      x: previousBounds.x + previousBounds.w + gutter,
      y: rowFirst.bounds.y,
    };
    return {
      position,
      cursor: {
        ...latestCursor,
        row: [...latestCursor.row, entry(position)],
        gridIds: [...latestCursor.gridIds, id],
      },
    };
  }

  // Row full: wrap to a new row just below the tallest card of this row
  const tallest = Math.max(...latestCursor.row.map(({ bounds }) => bounds.h));
  const position = {
    x: latestCursor.rowStartX,
    y: rowFirst.bounds.y + tallest + gutter,
  };
  return {
    position,
    cursor: {
      row: [entry(position)],
      rowStartX: latestCursor.rowStartX,
      gridIds: [...latestCursor.gridIds, id],
    },
  };
};

/** Whether `bounds` can fit fully on screen without zooming past `MIN_ZOOM`. */
const canFitWithinZoomCap = (
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
 */
const keepInView = (
  editor: Editor,
  bounds: CardBounds,
  cursor: GridCursor | null,
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
    const frame =
      gridBounds(editor, cursor, bounds) ?? editor.getCurrentPageBounds();
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
  /** Get the position for a card about to be created and advance the cursor. */
  place(id: TLShapeId, size: CardSize): CardPosition;

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

  const place = (id: TLShapeId, size: CardSize): CardPosition => {
    const slot = nextSlot(editor, id, size, cursor);
    cursor = slot.cursor;
    return slot.position;
  };

  // Cards pasted within the current task. tldraw's paste re-centers shapes
  // that land fully off-screen right after creating them, which would tear
  // a card off the grid — the veto below blocks that. A paste is fully
  // synchronous and has no 'finished' hook, so a queued microtask expires
  // each guard exactly when the operation ends
  const pastedThisTask = new Set<TLShapeId>();

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

      pastedThisTask.add(shape.id);
      queueMicrotask(() => pastedThisTask.delete(shape.id));

      return {
        ...shape,
        ...place(shape.id, { w: shape.props.w, h: shape.props.h }),
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

      keepInView(editor, mapShapeToBounds(shape), cursor);
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
      cursor = null;
      pastedThisTask.clear();
    },
  };
};
