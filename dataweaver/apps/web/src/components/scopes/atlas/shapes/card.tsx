import {
  HTMLContainer,
  type RecordProps,
  Rectangle2d,
  ShapeUtil,
  T,
  type TLShape,
} from 'tldraw';
import { Card } from '~/components/elements/card';
import type { CardSelection } from '~/components/elements/card/base';
import type {
  CardContentFields,
  CardSize,
  CardVariant,
} from '~/components/scopes/atlas/helpers';

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

  // Each card variant owns its own actions, content and footer; the shape just
  // hands it the state and content it needs to render itself.
  #renderCard = (shape: ShapeCard) => {
    const { variant, title, description, body, data, followUp } = shape.props;

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
          followUp={followUp}
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
          followUp={followUp}
        />
      );
    }

    console.warn(`Unsupported variant given '${variant}'.`);
    return null;
  };

  override component = (shape: ShapeCard) => {
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

  // Disable default TLDraw events
  override canResize = () => false;
  override hideResizeHandles = () => true;
  override hideRotateHandle = () => true;
  override hideSelectionBoundsBg = () => true;
  override hideSelectionBoundsFg = () => true;
  override getIndicatorPath = () => undefined;
}
