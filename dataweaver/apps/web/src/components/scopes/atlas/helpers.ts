import type { TLCreateShapePartial, TLShape, TLShapeId } from 'tldraw';
import type { CardState } from '~/components/elements/card/base';
import type { CardChartProps } from '~/components/elements/card/chart/chart';
import type { CardTextProps } from '~/components/elements/card/text';

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

const GRID = {
  columns: 4,
  stepX: 460,
  stepY: 600,
  originX: 120,
  originY: 120,
} as const;

/** A simple utility to get a new content's position based on index. */
export const gridPosition = (index: number): CardPosition => ({
  x: GRID.originX + (index % GRID.columns) * GRID.stepX,
  y: GRID.originY + Math.floor(index / GRID.columns) * GRID.stepY,
});

// Per-variant default canvas footprint
const VARIANT_SIZE: Record<CardVariant, CardSize> = {
  text: { w: 360, h: 440 },
  chart: { w: 420, h: 520 },
};

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
