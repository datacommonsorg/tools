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
import { toast } from '~/components/foundations/toaster/store';
import { IconBarChart } from '~/components/primitives/icons/bar_chart';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconPencil } from '~/components/primitives/icons/pencil';
import { useExportActions } from '~/components/scopes/atlas/export_provider';
import type {
  CardContentFields,
  CardSize,
  CardVariant,
} from '~/components/scopes/atlas/helpers';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { useDataWeaverStore } from '~/store';

export const CARD_DATA_ATTRIBUTE = 'data-card';

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
    data: T.arrayOf(T.object({ date: T.string, value: T.number })).optional(),
    facets: T.arrayOf(
      T.object({
        facetId: T.string,
        source: T.string,
        sourceUrl: T.string,
        unit: T.string,
        earliestDate: T.string,
        latestDate: T.string,
        observationCount: T.number,
        measurementMethod: T.string.optional(),
        observations: T.arrayOf(T.object({ date: T.string, value: T.number })),
      }),
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
    const { open: openExport } = useExportActions();

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
        {
          icon: IconBarChart,
          label: 'View chart',
          isDisabled: isLoading,

          // TODO: Support chart options here
          onClick: () =>
            toast(
              'Cart chart options not supported yet',
              'This feature will be coming in a future release. Stay tuned!',
            ),
        },
        exportAction,
        deleteAction,
      ];
    }

    return [exportAction, deleteAction];
  };

  #renderContent = (shape: ShapeCard, isLoading: boolean) => {
    const { variant, title, description, body, data, facets } = shape.props;

    if (variant === 'chart') {
      return (
        <Card.Chart
          title={title}
          description={description}
          data={data}
          facets={facets}
          isLoading={isLoading}
        />
      );
    }

    return (
      <Card.Text
        title={title}
        body={body}
        isLoading={isLoading}
        onAction={(href) => this.#handleAction(shape, href)}
      />
    );
  };

  #handleAction = (shape: ShapeCard, href: string) => {
    const params = new URLSearchParams(href.replace(/^#/, ''));
    const variableDcid = params.get('fetch');
    const placeDcid = params.get('place');
    if (!variableDcid || !placeDcid) return;

    const { cards, cardRegister } = useDataWeaverStore.getState();

    // Find the card entry for this shape to get the historyNodeId.
    const cardEntry = cards[shape.id];
    if (!cardEntry) return;

    // Deterministic ID prevents duplicates.
    const chartShapeId = `shape:${cardEntry.historyNodeId}__${placeDcid}__chart__${variableDcid}`;
    if (cards[chartShapeId]) return;

    cardRegister(
      chartShapeId,
      cardEntry.historyNodeId,
      'chart',
      placeDcid,
      variableDcid,
    );
  };

  #renderFooter = (shape: ShapeCard) => {
    const { runPrompt } = useQueryActions();
    const { followUp } = shape.props;

    // Only render follow-up button if the card has a follow-up query defined
    if (!followUp) return null;

    return (
      <Button
        size="small"
        variant="flat"
        tone="accent-subtle"
        icon={IconPencil}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => runPrompt(followUp)}
      >
        {followUp}
      </Button>
    );
  };

  override component = (shape: ShapeCard) => {
    const isLoading = shape.props.isLoading ?? false;

    return (
      <HTMLContainer
        // Marks the card in the DOM so that we can target it with CSS selectors
        // outside of this component (e.g. in the export menu)
        {...{ [CARD_DATA_ATTRIBUTE]: true }}
        style={{
          width: shape.props.w,
          height: shape.props.h,
          pointerEvents: 'auto',
        }}
      >
        <Card.Base
          isLoading={isLoading}
          selection={this.#getSelectionState(shape)}
          actions={this.#getActions(shape, isLoading)}
          content={this.#renderContent(shape, isLoading)}
          footer={this.#renderFooter(shape)}
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
