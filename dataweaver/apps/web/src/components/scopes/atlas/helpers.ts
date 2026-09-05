import type { TLCreateShapePartial, TLShape, TLShapeId } from 'tldraw';
import type { CardState } from '~/components/elements/card/base';
import type { CardChartProps } from '~/components/elements/card/chart/chart';
import type { CardSize } from '~/components/elements/card/config';
import type { CardTextProps } from '~/components/elements/card/text';
import type { ChartStyle } from '~/server/types';

interface BaseContent extends Partial<Pick<CardState, 'isLoading'>> {
  relatedQueries?: string[];
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
    Pick<
      CardChartProps,
      | 'title'
      | 'description'
      | 'data'
      | 'series'
      | 'facets'
      | 'seriesFacets'
      | 'parentPlaceDcid'
    > {
  variant: 'chart';
  chartStyle?: ChartStyle;
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

export type { CardSize };

/** A card's position and size together. */
export type CardBounds = CardPosition & CardSize;

/** The card shape as stored on the tldraw canvas. */
export type CardShape = TLShape<'card'>;

export { snapToGrid } from '~/functions/snap_to_grid';

/** Convert card content into `TLShape` for placement on the canvas. */
export const contentToShape = (
  shapeId: TLShapeId,
  content: AtlasContent,
  position: CardPosition,
  size: CardSize,
): TLCreateShapePartial<CardShape> => {
  const baseProps = {
    id: shapeId,
    x: position.x,
    y: position.y,
    type: 'card' as const,
  };

  const shapeProps = {
    ...size,
    isLoading: content.isLoading ?? false,
    relatedQueries: content.relatedQueries,
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
        series: content.series,
        facets: content.facets,
        seriesFacets: content.seriesFacets,
        chartStyle: content.chartStyle,
        parentPlaceDcid: content.parentPlaceDcid,
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
