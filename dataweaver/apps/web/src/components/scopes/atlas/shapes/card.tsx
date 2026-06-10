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
import { IconBarChart } from '~/components/primitives/icons/bar_chart';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconPencil } from '~/components/primitives/icons/pencil';
import { useExportActions } from '~/components/scopes/atlas/components/in_front_of_canvas/export/export_provider';
import type {
  CardContentFields,
  CardVariant,
} from '~/components/scopes/atlas/helpers';

type ShapeCardProps = CardContentFields & {
  w: number;
  h: number;
  variant: CardVariant;
  isLoading: boolean;
};

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
    variant: T.literalEnum('text', 'chart'),
    title: T.string.optional(),
    description: T.string.optional(),
    body: T.string.optional(),
    data: T.arrayOf(
      T.object({ year: T.number, emissions: T.number }),
    ).optional(),
    isLoading: T.boolean,
    followUp: T.string.optional(),
  };

  override getDefaultProps = (): ShapeCardProps => {
    return { w: 360, h: 440, variant: 'text', isLoading: false };
  };

  override getGeometry = (shape: ShapeCard) => {
    return new Rectangle2d({
      width: shape.props.w,
      height: shape.props.h,
      isFilled: true,
    });
  };

  #getActions = (
    shape: ShapeCard,
    isLoading: boolean,
    openExport: () => void,
  ) => {
    const deleteAction = {
      icon: IconDelete,
      label: 'Delete',
      onClick: () => this.editor.deleteShapes([shape.id]),
    };

    const exportAction = {
      icon: IconExport,
      label: 'Export',
      isDisabled: isLoading,
      onClick: () => {
        this.editor.select(shape.id);
        openExport();
      },
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
    const { w, h, isLoading, followUp } = shape.props;
    const isSelected = this.editor.getSelectedShapeIds().includes(shape.id);
    const { open: openExport } = useExportActions();

    return (
      <HTMLContainer style={{ width: w, height: h, pointerEvents: 'auto' }}>
        <Card.Base
          isLoading={isLoading}
          isSelected={isSelected}
          actions={this.#getActions(shape, isLoading, openExport)}
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
  override hideSelectionBoundsFg = () => true;
  override hideSelectionBoundsBg = () => true;
  override getIndicatorPath = () => undefined;
}
