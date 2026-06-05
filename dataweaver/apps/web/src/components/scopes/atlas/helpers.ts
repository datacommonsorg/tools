import type { TLCreateShapePartial, TLShape, TLShapeId } from 'tldraw';
import type { ChartDatum } from '~/components/elements/card/chart/data_chart_line';

export type CardVariant = 'text' | 'chart';

interface BaseContent {
  isLoading?: boolean;
  followUp?: string;
}

interface TextContent extends BaseContent {
  variant: 'text';
  title?: string;
  body?: string;
}

interface ChartContent extends BaseContent {
  variant: 'chart';
  title?: string;
  description?: string;
  data?: ChartDatum[];
}

/**
 * App-level description of a thing to mount on the canvas. The atlas only
 * renders cards; the variant decides which content fields are valid.
 */
export type AtlasContent = TextContent | ChartContent;

/**
 * Flat view of every possible content field — variant-specific fields become
 * optional. Used by the shape util, since tldraw stores props as a flat record.
 */
export type CardContentFields = Omit<TextContent, 'variant'> &
  Omit<ChartContent, 'variant'>;

interface Position {
  x: number;
  y: number;
}

const GRID = {
  columns: 4,
  stepX: 460,
  stepY: 600,
  originX: 120,
  originY: 120,
} as const;

/** A simple utility to get a new content's position based on index. */
export const gridPosition = (index: number): Position => ({
  x: GRID.originX + (index % GRID.columns) * GRID.stepX,
  y: GRID.originY + Math.floor(index / GRID.columns) * GRID.stepY,
});

// Per-variant default canvas footprint
const VARIANT_SIZE: Record<CardVariant, { w: number; h: number }> = {
  text: { w: 360, h: 440 },
  chart: { w: 420, h: 520 },
};

export const contentToShape = (
  shapeId: TLShapeId,
  content: AtlasContent,
  position: Position,
): TLCreateShapePartial<TLShape<'card'>> => {
  const baseProps = {
    id: shapeId,
    x: position.x,
    y: position.y,
    type: 'card' as const,
  };

  const shapeProps = {
    ...VARIANT_SIZE[content.variant],
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
