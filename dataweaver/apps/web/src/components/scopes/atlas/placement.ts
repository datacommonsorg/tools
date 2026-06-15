import type { Editor } from 'tldraw';
import { DISTANCE_FROM_OTHER_CARDS, KEEP_IN_VIEW_ANIMATION } from './config';
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

/**
 * Find where to place a new card of `size` so it clears every `occupied` card
 * by `DISTANCE_FROM_OTHER_CARDS`. Cards pack left-to-right from `origin` using
 * their real widths, wrapping to a new row only when the card would cross
 * `maxRight` (the row's right edge). Both axes are driven by the cards actually
 * on the canvas — no fixed cell size — so cards of any size pack tightly and
 * moving or deleting one frees its space.
 *
 * Without `anchor`, takes the first free slot in reading order (new query
 * cards). With `anchor` (e.g. cloning), takes the free slot nearest to it, so
 * the new card lands beside its source rather than back at the origin.
 */
const findVacantPosition = (
  occupied: CardBounds[],
  size: CardSize,
  origin: CardPosition,
  maxRight: number,
  anchor?: CardPosition,
): CardPosition => {
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

  // If we got an anchor: Drop the card in the free slot nearest the anchor
  // (the drop point), ignoring the row edge so it stays beside its source
  if (anchor) {
    const freeSlots = slots.filter((slot) => isFree(slot, size, occupied));
    freeSlots.sort(
      (a, b) => distanceSquared(a, anchor) - distanceSquared(b, anchor),
    );

    // If we got a nearest free slot, return it
    const [nearest] = freeSlots;
    if (nearest) return nearest;
  }

  // For other instances: The first free slot that fits within the row's right
  // edge — the origin always fits, starting a fresh row
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
 *
 * `reserved` holds footprints not yet committed to the store — e.g. sibling
 * clones being created in the same paste/duplicate batch — so cards placed in
 * one tick don't land on top of each other.
 */
export const placeCard = (
  editor: Editor,
  size: CardSize,
  anchor?: CardPosition,
  reserved: CardBounds[] = [],
): CardPosition => {
  const viewport = editor.getViewportPageBounds();
  const origin = {
    x: viewport.minX + DISTANCE_FROM_OTHER_CARDS,
    y: viewport.minY + DISTANCE_FROM_OTHER_CARDS,
  };
  const maxRight = viewport.maxX - DISTANCE_FROM_OTHER_CARDS;
  const occupied = [...cardBounds(editor), ...reserved];
  return findVacantPosition(occupied, size, origin, maxRight, anchor);
};

/**
 * Pan the camera to a freshly placed card if not fully visible. Ignores the
 * card if it already is, so filling a row that's on screen doesn't move camera.
 */
export const keepInView = (editor: Editor, bounds: CardBounds): void => {
  const viewport = editor.getViewportPageBounds();

  const fullyVisible =
    bounds.x >= viewport.minX &&
    bounds.y >= viewport.minY &&
    bounds.x + bounds.w <= viewport.maxX &&
    bounds.y + bounds.h <= viewport.maxY;

  // Ignore if already fully visible
  if (fullyVisible) return;

  editor.centerOnPoint(
    { x: bounds.x + bounds.w / 2, y: bounds.y + bounds.h / 2 },
    { animation: KEEP_IN_VIEW_ANIMATION },
  );
};
