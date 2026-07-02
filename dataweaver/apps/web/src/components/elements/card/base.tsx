'use client';

import {
  type ComponentPropsWithRef,
  type ComponentType,
  type ReactNode,
  useRef,
} from 'react';
import type { TLShapeId } from 'tldraw';
import { Button } from '~/components/elements/button';
import { CARD_VARIANT_MAX } from '~/components/scopes/atlas/config';
import type { CardVariant } from '~/components/scopes/atlas/helpers';
import { useCachedResizeValues } from '~/hooks/use_cached_resize_values';
import s from './base.module.scss';
import { useCardAutoHeight } from './use_card_auto_height';
import { useCardClearTextSelection } from './use_card_clear_text_selection';
import { useCardDragHandle } from './use_card_drag_handle';

/**
 * How the card is selected on the canvas:
 * - `none`: Not selected
 * - `single`: The only selected shape
 * - `multiple`: Selected alongside other shapes
 */
export type CardSelection = 'none' | 'single' | 'multiple';

/** The card's two orthogonal, independently-settable states. */
export interface CardState {
  isLoading: boolean;
  selection: CardSelection;
}

interface CardAction {
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;
  label: string;
  onClick?: () => void;

  /** @default false */
  isDisabled?: boolean;

  /** @default false */
  isActive?: boolean;
}

interface CardProps extends CardState {
  id: TLShapeId;
  variant: CardVariant;
  actions: CardAction[];
  children: ReactNode;
}

export const CardBase = ({
  id,
  variant,
  isLoading,
  selection,
  actions,
  children,
}: CardProps) => {
  const childrenContainerRef = useRef<HTMLDivElement>(null);

  useCardAutoHeight(childrenContainerRef, id, CARD_VARIANT_MAX[variant].h);

  useCardClearTextSelection(childrenContainerRef, id);

  const startDragging = useCardDragHandle(id);

  const getCachedCanScroll = useCachedResizeValues((element: HTMLElement) => {
    return element.scrollHeight > element.clientHeight;
  });

  return (
    <article
      className={s.container}
      data-is-loading={isLoading}
      data-selection={selection}
    >
      <div className={s['actions-container']} onPointerDown={startDragging}>
        {actions.map((action, index) => (
          <Button
            key={index}
            icon={action.icon}
            size="large"
            variant="flat"
            tone="card-action"
            aria-label={action.label}
            aria-pressed={action.isActive}
            // Prevent tldraw from triggering canvas gestures (e.g. dragging)
            onPointerDown={(event) => event.stopPropagation()}
            onClick={action.onClick}
            isDisabled={action.isDisabled}
          />
        ))}
      </div>

      <div
        ref={childrenContainerRef}
        className={s['children-container']}
        // TLDraw captures all wheel events; this ensures that cards can be
        // scrolled when children here can scroll
        onWheelCapture={(event) => {
          if (getCachedCanScroll(false, event.currentTarget)) {
            event.stopPropagation();
          }
        }}
        // Once the card is the single selection, reserve dragging for the
        // actions bar: stop the canvas from starting a gesture so the content
        // stays selectable/highlightable. While unselected or multi-selected we
        // let events through so tldraw keeps handling select/multi-select/drag
        onPointerDown={
          selection === 'single'
            ? (event) => event.stopPropagation()
            : undefined
        }
      >
        {children}
      </div>
    </article>
  );
};
