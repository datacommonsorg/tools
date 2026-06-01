import {
  HTMLContainer,
  type RecordProps,
  Rectangle2d,
  ShapeUtil,
  T,
  type TLShape,
} from 'tldraw';
import { Button } from '~/components/elements/button';
import { Card } from '~/components/elements/card';
import type { CardState } from '~/components/elements/card/base';
import type { ChartDatum } from '~/components/elements/card/chart/data_line_chart';
import { IconBarChart } from '~/components/primitives/icons/bar_chart';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconPencil } from '~/components/primitives/icons/pencil';

interface CardChartShapeProps {
  w: number;
  h: number;
  title?: string;
  description?: string;
  data?: ChartDatum[];
  isLoading: boolean;
}

// Register the custom shape within tldraw
declare module 'tldraw' {
  interface TLGlobalShapePropsMap {
    'card-chart': CardChartShapeProps;
  }
}

export type CardChartShape = TLShape<'card-chart'>;

export class CardChartShapeUtil extends ShapeUtil<CardChartShape> {
  static override type = 'card-chart' as const;

  static override props: RecordProps<CardChartShape> = {
    w: T.number,
    h: T.number,
    title: T.string.optional(),
    description: T.string.optional(),
    data: T.arrayOf(
      T.object({ year: T.number, emissions: T.number }),
    ).optional(),
    isLoading: T.boolean,
  };

  override getDefaultProps = (): CardChartShapeProps => {
    return { w: 420, h: 520, data: [], isLoading: false };
  };

  override getGeometry = (shape: CardChartShape) => {
    return new Rectangle2d({
      width: shape.props.w,
      height: shape.props.h,
      isFilled: true,
    });
  };

  #getState = (shape: CardChartShape): CardState => {
    if (shape.props.isLoading) return 'loading';

    const isSelected = this.editor.getSelectedShapeIds().includes(shape.id);
    if (isSelected) return 'selected';

    return 'default';
  };

  override component = (shape: CardChartShape) => {
    const { w, h, title, description, data, isLoading } = shape.props;

    return (
      <HTMLContainer style={{ width: w, height: h, pointerEvents: 'auto' }}>
        <Card.Base
          state={this.#getState(shape)}
          actions={[
            // TODO: Hook up action(s) once supported
            { icon: IconBarChart, label: 'View chart' },
            { icon: IconExport, label: 'Export' },
            {
              icon: IconDelete,
              label: 'Delete',
              onClick: () => this.editor.deleteShapes([shape.id]),
            },
          ]}
          content={
            <Card.Chart
              title={title}
              description={description}
              data={data}
              isLoading={isLoading}
            />
          }
          footer={
            <Button
              icon={IconPencil}
              onPointerDown={(event) => event.stopPropagation()}
            >
              {/* TODO: Get this from the shape's data. */}
              Follow up question based on this cards info?
            </Button>
          }
        />
      </HTMLContainer>
    );
  };

  // Disable default TLDraw events
  override canResize = () => false;
  override hideSelectionBoundsFg = () => true;
  override hideSelectionBoundsBg = () => true;
  override getIndicatorPath = () => undefined;
}
