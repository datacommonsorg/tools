import type { Editor, TLCreateShapePartial, TLShape, TLShapeId } from 'tldraw';
import type { CardState } from '~/components/elements/card/base';
import type { CardChartProps } from '~/components/elements/card/chart/chart';
import type { CardTextProps } from '~/components/elements/card/text';
import {
  CARD_VARIANT_SIZE,
  DISTANCE_FROM_OTHER_CARDS,
  KEEP_IN_VIEW_ANIMATION,
} from './config';

interface BaseContent extends Partial<Pick<CardState, 'isLoading'>> {
  followUp?: string;
}

interface TextContent
  extends BaseContent,
    Pick<CardTextProps, 'title' | 'body'> {
  variant: 'text';
}

interface ChartContent
  extends BaseContent,
    Pick<CardChartProps, 'title' | 'description' | 'data'> {
  variant: 'chart';
}

export type AtlasContent = TextContent | ChartContent;

export type CardVariant = AtlasContent['variant'];

/** Flat view of every possible card content field. */
export type CardContentFields = Omit<TextContent, 'variant'> &
  Omit<ChartContent, 'variant'>;

export interface CardPosition {
  x: number;
  y: number;
}

export interface CardSize {
  w: number;
  h: number;
}

/** A card's position and size together. */
export type CardBounds = CardPosition & CardSize;

/** Whether two card footprints sit closer than `gap` on both axes. */
const isTooClose = (a: CardBounds, b: CardBounds, gap: number): boolean => {
  return (
    a.x < b.x + b.w + gap &&
    b.x < a.x + a.w + gap &&
    a.y < b.y + b.h + gap &&
    b.y < a.y + a.h + gap
  );
};

/**
 * Find where to place a new card of `size` so it clears every `occupied` card
 * by `DISTANCE_FROM_OTHER_CARDS`. Cards pack left-to-right from
 * `FIRST_CARD_POSITION` using their real widths, wrapping to a new row only when
 * the card would cross `maxRight` (the row's right edge). Both axes are driven
 * by the cards actually on the canvas — no fixed cell size — so cards of any
 * size pack tightly and moving or deleting one frees its space.
 *
 * Without `anchor`, takes the first free slot in reading order (new query
 * cards). With `anchor` (e.g. cloning), takes the free slot nearest to it, so
 * the new card lands beside its source rather than back at the origin.
 */
const findVacantPosition = (
  occupied: CardBounds[],
  size: CardSize,
  maxRight: number,
  anchor?: CardPosition,
): CardPosition => {
  const isClear = (candidate: CardBounds): boolean =>
    !occupied.some((card) =>
      isTooClose(candidate, card, DISTANCE_FROM_OTHER_CARDS),
    );

  // Candidate corners: the origin, plus just past the right edge (for x) and
  // bottom edge (for y) of every card, so a new card can butt up against an
  // existing one. Sorted so the topmost-leftmost gap is filled first; the
  // lowest y is always below every card, guaranteeing an empty fallback row.
  const candidateXs = [
    DISTANCE_FROM_OTHER_CARDS,
    ...occupied.map((card) => card.x + card.w + DISTANCE_FROM_OTHER_CARDS),
  ].sort((a, b) => a - b);
  const candidateYs = [
    DISTANCE_FROM_OTHER_CARDS,
    ...occupied.map((card) => card.y + card.h + DISTANCE_FROM_OTHER_CARDS),
  ].sort((a, b) => a - b);

  let best: CardPosition | undefined;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const y of candidateYs) {
    for (const x of candidateXs) {
      // Must stay within the row's right edge — except at the origin, where a
      // card always starts a fresh row even if it's wider than that edge.
      const fitsRow = x + size.w <= maxRight || x === DISTANCE_FROM_OTHER_CARDS;
      if (!fitsRow) continue;

      const candidate = { x, y, ...size };
      if (!isClear(candidate)) continue;

      // No anchor: the first free slot in reading order wins.
      if (!anchor) return { x, y };

      // Anchor (cloning): keep the free slot closest to it.
      const distance = (x - anchor.x) ** 2 + (y - anchor.y) ** 2;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = { x, y };
      }
    }
  }

  return best ?? { x: DISTANCE_FROM_OTHER_CARDS, y: DISTANCE_FROM_OTHER_CARDS };
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
 * on the page, packed left-to-right and wrapping once a row reaches the canvas
 * width.
 *
 * The wrap width is the canvas's on-screen size (a stable page-space span),
 * never the live viewport bounds — so the layout doesn't shift as the user
 * zooms or pans. A right inset mirrors the origin's left inset.
 *
 * With `anchor` (cloning) the card lands beside the source rather than at the
 * origin.
 */
export const placeCard = (
  editor: Editor,
  size: CardSize,
  anchor?: CardPosition,
): CardPosition => {
  const canvasWidth = editor.getViewportScreenBounds().w;
  const maxRight = canvasWidth - DISTANCE_FROM_OTHER_CARDS;
  return findVacantPosition(cardBounds(editor), size, maxRight, anchor);
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

/** Convert card content into `TLShape` for placement on the canvas. */
export const contentToShape = (
  shapeId: TLShapeId,
  content: AtlasContent,
  position: CardPosition,
): TLCreateShapePartial<TLShape<'card'>> => {
  const baseProps = {
    id: shapeId,
    x: position.x,
    y: position.y,
    type: 'card' as const,
  };

  const shapeProps = {
    ...CARD_VARIANT_SIZE[content.variant],
    isLoading: content.isLoading ?? false,
    followUp: content.followUp,
  };

  if (content.variant === 'chart') {
    return {
      ...baseProps,
      props: {
        ...shapeProps,
        variant: 'chart',
        title: content.title,
        description: content.description,
        data: content.data,
      },
    };
  }

  return {
    ...baseProps,
    props: {
      ...shapeProps,
      variant: 'text',
      title: content.title,
      body: content.body,
    },
  };
};
