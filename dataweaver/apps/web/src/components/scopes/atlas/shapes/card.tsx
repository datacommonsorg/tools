import {
  HTMLContainer,
  type RecordProps,
  Rectangle2d,
  resizeBox,
  ShapeUtil,
  T,
  type TLResizeInfo,
  type TLShape,
  type TLShapePartial,
} from 'tldraw';
import { Card } from '~/components/elements/card';
import type { CardSelection } from '~/components/elements/card/base';
import { CARD_SIZE_MIN, GRID_SIZE } from '~/components/scopes/atlas/config';
import {
  type CardContentFields,
  type CardSize,
  type CardVariant,
  snapToGrid,
} from '~/components/scopes/atlas/helpers';
import type { ChartStyle } from '~/server/types';

export const CARD_DATA_ATTRIBUTE = 'data-card';

interface ShapeCardProps extends CardContentFields, CardSize {
  variant?: CardVariant;

  /**
   * Set once the user drags a resize handle. While true, `useCardAutoHeight`
   * stops syncing `h` to the content so the manual size sticks.
   */
  isManuallyResized?: boolean;

  /** Persisted chart style override. */
  chartStyle?: ChartStyle;
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
    series: T.arrayOf(
      T.object({
        key: T.string,
        label: T.string,
        data: T.arrayOf(T.object({ date: T.string, value: T.number })),
        connectNulls: T.boolean.optional(),
      }),
    ).optional(),
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
    seriesFacets: T.dict(
      T.string,
      T.arrayOf(
        T.object({
          facetId: T.string,
          source: T.string,
          sourceUrl: T.string,
          unit: T.string,
          earliestDate: T.string,
          latestDate: T.string,
          observationCount: T.number,
          measurementMethod: T.string.optional(),
          observations: T.arrayOf(
            T.object({ date: T.string, value: T.number }),
          ),
        }),
      ),
    ).optional(),
    isLoading: T.boolean.optional(),
    isManuallyResized: T.boolean.optional(),
    chartStyle: T.literalEnum(
      'bar-vertical',
      'bar-horizontal',
      'line',
    ).optional(),
    relatedQueries: T.arrayOf(T.string).optional(),
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

  // Each card variant owns its own actions, content and footer; the shape just
  // hands it the state and content it needs to render itself.
  #renderCard = (shape: ShapeCard) => {
    const {
      variant,
      title,
      description,
      body,
      data,
      series,
      facets,
      seriesFacets,
      relatedQueries,
      chartStyle,
    } = shape.props;

    const isLoading = shape.props.isLoading ?? false;
    const selection = this.#getSelectionState(shape);

    if (variant === 'text') {
      return (
        <Card.Text
          id={shape.id}
          isLoading={isLoading}
          selection={selection}
          title={title}
          body={body}
          relatedQueries={relatedQueries}
        />
      );
    }

    if (variant === 'chart') {
      return (
        <Card.Chart
          id={shape.id}
          isLoading={isLoading}
          selection={selection}
          title={title}
          description={description}
          data={data}
          series={series}
          facets={facets}
          seriesFacets={seriesFacets}
          relatedQueries={relatedQueries}
          chartStyle={chartStyle}
        />
      );
    }

    console.warn(`Unsupported variant given '${variant}'.`);
    return null;
  };

  override component = (shape: ShapeCard) => {
    const variant = shape.props.variant;
    if (!variant) throw new Error('Card shape missing variant.');

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
        {this.#renderCard(shape)}
      </HTMLContainer>
    );
  };

  override hideRotateHandle = () => true;
  override hideSelectionBoundsBg = () => true;
  override hideSelectionBoundsFg = () => true;
  override getIndicatorPath = () => undefined;

  override onResize = (shape: ShapeCard, info: TLResizeInfo<ShapeCard>) => {
    const resized = resizeBox(shape, info, {
      minWidth: CARD_SIZE_MIN.w,
      minHeight: CARD_SIZE_MIN.h,
    });

    // Chart cards always snap back to their content height after resize, so
    // don't flag them as manually sized. Text cards keep the user's height.
    if (shape.props.variant === 'chart') return resized;

    return { ...resized, props: { ...resized.props, isManuallyResized: true } };
  };

  // Dragging and resizing stay free — only the value at pointer-up snaps to
  // the grid, so it lands on the same dots the `Grid` background renders.
  override onTranslateEnd = (
    _initial: ShapeCard,
    shape: ShapeCard,
  ): TLShapePartial<ShapeCard> => ({
    id: shape.id,
    type: shape.type,
    x: snapToGrid(shape.x, GRID_SIZE),
    y: snapToGrid(shape.y, GRID_SIZE),
  });

  override onResizeEnd = (
    _initial: ShapeCard,
    shape: ShapeCard,
  ): TLShapePartial<ShapeCard> => {
    // Chart cards auto-manage `h` via useCardAutoHeight, which snaps it back
    // to content height post-resize — snapping it here too just adds flicker.
    const isChart = shape.props.variant === 'chart';

    return {
      id: shape.id,
      type: shape.type,
      x: snapToGrid(shape.x, GRID_SIZE),
      y: snapToGrid(shape.y, GRID_SIZE),
      props: {
        w: Math.max(CARD_SIZE_MIN.w, snapToGrid(shape.props.w, GRID_SIZE)),
        ...(isChart
          ? {}
          : {
              h: Math.max(
                CARD_SIZE_MIN.h,
                snapToGrid(shape.props.h, GRID_SIZE),
              ),
            }),
      },
    };
  };
}
