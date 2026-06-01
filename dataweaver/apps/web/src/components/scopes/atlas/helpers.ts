import { createShapeId, type TLCreateShapePartial } from 'tldraw';
import type { ChartDatum } from '~/components/elements/card/chart/data_line_chart';
import type { CardChartShape } from './shapes/card_chart';
import type { CardTextShape } from './shapes/card_text';

/**
 * App-level description of a thing to mount on the canvas. This is the layer's
 * public vocabulary — callers describe content, not tldraw shapes.
 */
export type AtlasContent =
  | { kind: 'card'; title: string; body?: string; isLoading?: boolean }
  | {
      kind: 'card-chart';
      title: string;
      description: string;
      data: ChartDatum[];
    };

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

type AtlasShapePartial =
  | TLCreateShapePartial<CardTextShape>
  | TLCreateShapePartial<CardChartShape>;

export const contentToShape = (
  content: AtlasContent,
  position: Position,
): AtlasShapePartial | null => {
  const baseProps = {
    id: createShapeId(),
    x: position.x,
    y: position.y,
  };

  switch (content.kind) {
    case 'card':
      return {
        ...baseProps,
        type: 'card',
        props: {
          w: 360,
          h: 440,
          title: content.title,
          body: content.body ?? '',
          isLoading: content.isLoading ?? false,
        },
      };

    case 'card-chart':
      return {
        ...baseProps,
        type: 'card-chart',
        props: {
          w: 420,
          h: 520,
          title: content.title,
          description: content.description,
          data: content.data,
        },
      };

    default: {
      console.warn(`Attempting to draw unsupported content in Atlas:`, content);

      // Note: We purposely don't want to throw to improve DX when iterating on
      // content types. If there's not content type we can just ignore it
      return null;
    }
  }
};
