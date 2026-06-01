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
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconPencil } from '~/components/primitives/icons/pencil';

interface CardTextShapeProps {
  w: number;
  h: number;
  title?: string;
  body?: string;
  isLoading: boolean;
}

// Register the custom shape within tldraw
declare module 'tldraw' {
  interface TLGlobalShapePropsMap {
    card: CardTextShapeProps;
  }
}

export type CardTextShape = TLShape<'card'>;

export class CardTextShapeUtil extends ShapeUtil<CardTextShape> {
  static override type = 'card' as const;

  static override props: RecordProps<CardTextShape> = {
    w: T.number,
    h: T.number,
    title: T.string.optional(),
    body: T.string.optional(),
    isLoading: T.boolean,
  };

  override getDefaultProps = (): CardTextShapeProps => {
    return { w: 360, h: 440, isLoading: false };
  };

  override getGeometry = (shape: CardTextShape) => {
    return new Rectangle2d({
      width: shape.props.w,
      height: shape.props.h,
      isFilled: true,
    });
  };

  #getState = (shape: CardTextShape): CardState => {
    if (shape.props.isLoading) return 'loading';

    const isSelected = this.editor.getSelectedShapeIds().includes(shape.id);
    if (isSelected) return 'selected';

    return 'default';
  };

  override component = (shape: CardTextShape) => {
    const { w, h, title, body, isLoading } = shape.props;

    return (
      <HTMLContainer style={{ width: w, height: h, pointerEvents: 'auto' }}>
        <Card.Base
          state={this.#getState(shape)}
          actions={[
            // TODO: Hook up action once supported
            { icon: IconExport, label: 'Export' },
            {
              icon: IconDelete,
              label: 'Delete',
              onClick: () => this.editor.deleteShapes([shape.id]),
            },
          ]}
          content={
            <Card.Text title={title} body={body} isLoading={isLoading} />
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
