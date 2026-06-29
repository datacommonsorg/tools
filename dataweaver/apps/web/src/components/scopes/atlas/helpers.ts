import type { TLCreateShapePartial, TLShape, TLShapeId } from 'tldraw';
import type { CardState } from '~/components/elements/card/base';
import type { CardChartProps } from '~/components/elements/card/chart/chart';
import type { CardTextProps } from '~/components/elements/card/text';
import { CARD_VARIANT_SIZE } from './config';

interface BaseContent extends Partial<Pick<CardState, 'isLoading'>> {
  followUp?: string;
}

interface TextContent
  extends BaseContent,
    Pick<CardTextProps, 'title' | 'body'> {
  variant: 'text';
}

interface TableContent
  extends BaseContent,
    Pick<CardTextProps, 'title' | 'body'> {
  variant: 'table';
}

interface ChartContent
  extends BaseContent,
    Pick<CardChartProps, 'title' | 'description' | 'data' | 'facets'> {
  variant: 'chart';
}

export type AtlasContent = TextContent | TableContent | ChartContent;

export type CardVariant = AtlasContent['variant'];

/** Flat view of every possible card content field. */
export type CardContentFields = Omit<TextContent, 'variant'> &
  Omit<TableContent, 'variant'> &
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
        facets: content.facets,
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
