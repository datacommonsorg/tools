import type { Box, Editor } from 'tldraw';
import {
  DISTANCE_FROM_OTHER_CARDS,
  KEEP_IN_VIEW_ANIMATION,
  MIN_ZOOM,
} from './config';
import type { CardBounds, CardPosition, CardSize } from './helpers';

/** Whether two card footprints sit closer than `gap` on both axes. */
const isTooClose = (a: CardBounds, b: CardBounds, gap: number): boolean => {
  return (
    a.x < b.x + b.w + gap &&
    b.x < a.x + a.w + gap &&
    a.y < b.y + b.h + gap &&
    b.y < a.y + a.h + gap
  );
};

/** Whether `candidate` clears every `occupied` card by given `gap`. */
const isClear = (
  candidate: CardBounds,
  occupied: CardBounds[],
  gap: number,
): boolean => {
  return !occupied.some((card) => isTooClose(candidate, card, gap));
};

/** Whether a card of `size` placed at `slot` clears every `occupied` card. */
const isFree = (
  slot: CardPosition,
  size: CardSize,
  occupied: CardBounds[],
): boolean => {
  return isClear({ ...slot, ...size }, occupied, DISTANCE_FROM_OTHER_CARDS);
};

/**
 * Whether a card of `size` at `slot` stays within the row's right edge
 * (`maxRight`), or sits at `originX` where it always starts a fresh row.
 */
const fitsRow = (
  slot: CardPosition,
  size: CardSize,
  maxRight: number,
  originX: number,
): boolean => {
  return slot.x + size.w <= maxRight || slot.x === originX;
};

/**
 * Sorted candidate edges along one axis: the `start` (origin), an `at` value
 * (the anchor, if any), and just past every card's far edge, so a new card can
 * butt up against an existing one. Sorted so the topmost-leftmost gap fills
 * first; the last value always sits past every card for an empty fallback slot.
 */
const candidateAxis = (
  occupied: CardBounds[],
  start: number,
  far: (card: CardBounds) => number,
  anchor?: number,
): number[] => {
  const at = anchor === undefined ? [] : [anchor];
  return [start, ...at, ...occupied.map(far)].sort((a, b) => a - b);
};

/** Squared distance between two points. */
const distanceSquared = (a: CardPosition, b: CardPosition): number => {
  return (a.x - b.x) ** 2 + (a.y - b.y) ** 2;
};

/** Whether a card of `size` at `slot` overlaps the visible `viewport` */
const isOnScreen = (
  slot: CardPosition,
  size: CardSize,
  viewport: Box,
): boolean => {
  return (
    slot.x < viewport.maxX &&
    slot.x + size.w > viewport.minX &&
    slot.y < viewport.maxY &&
    slot.y + size.h > viewport.minY
  );
};

/**
 * Find where to place a new card of `size` so it clears every `occupied` card
 * by `DISTANCE_FROM_OTHER_CARDS`. Cards pack left-to-right from the viewport's
 * top-left, wrapping to a new row only when the card would cross the viewport's
 * right edge. Both axes are driven by the cards actually on the canvas — no
 * fixed cell size — so cards of any size pack tightly and moving or deleting one
 * frees its space.
 *
 * Without `anchor`, takes the first free slot in reading order (new query
 * cards). With `anchor` (e.g. cloning), takes the free slot nearest to it that
 * still overlaps the viewport — staying on-screen matters because tldraw's
 * paste re-centers any shape that lands fully off-screen, which would tear the
 * card away from where we placed it (and from where the camera follows it).
 */
const findVacantPosition = (
  occupied: CardBounds[],
  size: CardSize,
  viewport: Box,
  anchor?: CardPosition,
): CardPosition => {
  const origin = {
    x: viewport.minX + DISTANCE_FROM_OTHER_CARDS,
    y: viewport.minY + DISTANCE_FROM_OTHER_CARDS,
  };
  const candidatesX = candidateAxis(
    occupied,
    origin.x,
    (c) => c.x + c.w + DISTANCE_FROM_OTHER_CARDS,
    anchor ? anchor.x : undefined,
  );
  const candidatesY = candidateAxis(
    occupied,
    origin.y,
    (c) => c.y + c.h + DISTANCE_FROM_OTHER_CARDS,
    anchor ? anchor.y : undefined,
  );

  // Every candidate slot, in reading order (top-to-bottom, left-to-right)
  const slots = candidatesY.flatMap((y) => candidatesX.map((x) => ({ x, y })));

  // Cloning: the free slot nearest the anchor (drop point) that still overlaps
  // the viewport, so tldraw's paste leaves it where we put it
  if (anchor) {
    const freeSlots = slots.filter(
      (slot) =>
        isFree(slot, size, occupied) && isOnScreen(slot, size, viewport),
    );
    freeSlots.sort(
      (a, b) => distanceSquared(a, anchor) - distanceSquared(b, anchor),
    );

    const [nearest] = freeSlots;
    if (nearest) return nearest;
  }

  // New card (or clone with nowhere free on-screen): the first free slot that
  // fits within the row's right edge — the origin always fits, starting a row
  const maxRight = viewport.maxX - DISTANCE_FROM_OTHER_CARDS;
  const nearest = slots.find(
    (slot) =>
      fitsRow(slot, size, maxRight, origin.x) && isFree(slot, size, occupied),
  );
  if (nearest) return nearest;

  // If we got here - just render at origin
  return origin;
};

/** Footprints of every card currently on the page. */
const cardBounds = (editor: Editor): CardBounds[] => {
  const bounds: CardBounds[] = [];

  for (const shape of editor.getCurrentPageShapes()) {
    if (shape.type === 'card') {
      bounds.push({
        x: shape.x,
        y: shape.y,
        w: shape.props.w,
        h: shape.props.h,
      });
    }
  }

  return bounds;
};

/**
 * Where a new card of `size` should land: a vacant slot given the cards already
 * on the page, packed left-to-right and wrapping when a row reaches the visible
 * right edge — so rows fill the width that's actually on screen.
 *
 * The origin and right edge track the viewport (same page-space units as the
 * card coords, so the bounds are correct at any zoom), meaning cards pack from
 * the top-left of wherever the camera is looking — pan left and the next cards
 * land left of the previous spot. With `anchor` (cloning) the card lands beside
 * the source rather than at the origin.
 */
export const placeCard = (
  editor: Editor,
  size: CardSize,
  anchor?: CardPosition,
): CardPosition => {
  const viewport = editor.getViewportPageBounds();
  return findVacantPosition(cardBounds(editor), size, viewport, anchor);
};

/**
 * Whether a card within given page `bounds` can fit fully on screen without
 * zooming out past `MIN_ZOOM`. This is used to decide whether to zoom out to
 * frame all cards when a new card is placed, or just pan to the new card so it
 * lands on-screen.
 */
const canFitWithinZoomCap = (editor: Editor, bounds: Box): boolean => {
  // Degenerate bounds would divide to Infinity below and wrongly report a fit
  if (bounds.w <= 0 || bounds.h <= 0) return false;

  const screenBounds = editor.getViewportScreenBounds();

  const fitZoom = Math.min(
    (screenBounds.width - DISTANCE_FROM_OTHER_CARDS) / bounds.w,
    (screenBounds.height - DISTANCE_FROM_OTHER_CARDS) / bounds.h,
  );

  return fitZoom >= MIN_ZOOM;
};

/**
 * Reveal a freshly placed card. This follows 3 steps:
 * 1. If it already fits fully in the viewport, leave the camera be.
 * 2. If we can zoom out to frame every card at once, do that so the new card
 *    shows up in the context of the whole set
 * 3. We couldn't fit everything without hitting the min-zoom cap, so just pan
 *    to the new card so it lands on-screen
 */
export const keepInView = (editor: Editor, bounds: CardBounds): void => {
  const viewport = editor.getViewportPageBounds();

  const fullyVisible =
    bounds.x >= viewport.minX &&
    bounds.y >= viewport.minY &&
    bounds.x + bounds.w <= viewport.maxX &&
    bounds.y + bounds.h <= viewport.maxY;

  // Already fully on screen — don't move the camera at all
  if (fullyVisible) return;

  // If we can fit everything within the zoom cap - zoom to fit
  const pageBounds = editor.getCurrentPageBounds();
  if (pageBounds && canFitWithinZoomCap(editor, pageBounds)) {
    editor.zoomToBounds(pageBounds, {
      inset: DISTANCE_FROM_OTHER_CARDS,
      animation: KEEP_IN_VIEW_ANIMATION,
    });
    return;
  }

  // Fitting everything would blow past the zoom cap — just move to the new card
  editor.centerOnPoint(
    { x: bounds.x + bounds.w / 2, y: bounds.y + bounds.h / 2 },
    { animation: KEEP_IN_VIEW_ANIMATION },
  );
};
