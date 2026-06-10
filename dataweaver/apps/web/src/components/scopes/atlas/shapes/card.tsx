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
import type { CardSelection } from '~/components/elements/card/base';
import { IconBarChart } from '~/components/primitives/icons/bar_chart';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconPencil } from '~/components/primitives/icons/pencil';
import type {
  CardContentFields,
  CardSize,
  CardVariant,
} from '~/components/scopes/atlas/helpers';

interface ShapeCardProps extends CardContentFields, CardSize {
  variant?: CardVariant;
}

// Register the custom shape within tldraw
declare module 'tldraw' {
  interface TLGlobalShapePropsMap {
    card: ShapeCardProps;
  }
}

type ShapeCard = TLShape<'card'>;

export class ShapeCardUtil extends ShapeUtil<ShapeCard> {
  static override type = 'card' as const;

  static override props: RecordProps<ShapeCard> = {
    w: T.number,
    h: T.number,
    variant: T.literalEnum('text', 'chart').optional(),
    title: T.string.optional(),
    description: T.string.optional(),
    body: T.string.optional(),
    data: T.arrayOf(
      T.object({ year: T.number, emissions: T.number }),
    ).optional(),
    isLoading: T.boolean.optional(),
    followUp: T.string.optional(),
  };

  override getDefaultProps = (): ShapeCardProps => {
    return { w: 360, h: 440 };
  };

  override getGeometry = (shape: ShapeCard) => {
    return new Rectangle2d({
      width: shape.props.w,
      height: shape.props.h,
      isFilled: true,
    });
  };

  #getSelectionState = (shape: ShapeCard): CardSelection => {
    const selectedIds = this.editor.getSelectedShapeIds();
    const isSelected = selectedIds.includes(shape.id);
    if (!isSelected) return 'none';
    return selectedIds.length > 1 ? 'multiple' : 'single';
  };

  #getActions = (shape: ShapeCard, isLoading: boolean) => {
    const deleteAction = {
      icon: IconDelete,
      label: 'Delete',
      onClick: () => this.editor.deleteShapes([shape.id]),
    };

    // TODO: Hook up action(s) once supported
    const exportAction = {
      icon: IconExport,
      label: 'Export',
      isDisabled: isLoading,
    };

    if (shape.props.variant === 'chart') {
      return [
        { icon: IconBarChart, label: 'View chart', isDisabled: isLoading },
        exportAction,
        deleteAction,
      ];
    }

    return [exportAction, deleteAction];
  };

  #renderContent = (shape: ShapeCard, isLoading: boolean) => {
    const { variant, title, description, body, data } = shape.props;

    if (variant === 'chart') {
      return (
        <Card.Chart
          title={title}
          description={description}
          data={data}
          isLoading={isLoading}
        />
      );
    }

    return <Card.Text title={title} body={body} isLoading={isLoading} />;
  };

  override component = (shape: ShapeCard) => {
    const { w, h, followUp } = shape.props;
    const isLoading = shape.props.isLoading ?? false;

    return (
      <HTMLContainer style={{ width: w, height: h, pointerEvents: 'auto' }}>
        <Card.Base
          isLoading={isLoading}
          selection={this.#getSelectionState(shape)}
          actions={this.#getActions(shape, isLoading)}
          content={this.#renderContent(shape, isLoading)}
          footer={
            followUp && (
              <Button
                icon={IconPencil}
                size="small"
                onPointerDown={(event) => event.stopPropagation()}
              >
                {followUp}
              </Button>
            )
          }
        />
      </HTMLContainer>
    );
  };

  // Disable default TLDraw events
  override canResize = () => false;
  override hideResizeHandles = () => true;
  override hideRotateHandle = () => true;
  override hideSelectionBoundsBg = () => true;
  override hideSelectionBoundsFg = () => true;
  override getIndicatorPath = () => undefined;
}
