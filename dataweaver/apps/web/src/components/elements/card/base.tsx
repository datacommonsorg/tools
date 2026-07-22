'use client';

import type {
  ComponentPropsWithRef,
  ComponentType,
  ReactNode,
  RefObject,
} from 'react';
import type { TLShapeId } from 'tldraw';
import { Button } from '~/components/elements/button';
import { mergeClassNames } from '~/functions/merge_class_names';
import s from './base.module.scss';
import { useCardClearTextSelection } from './use_card_clear_text_selection';
import { useCardDragHandle } from './use_card_drag_handle';
import { useCardTextClipboard } from './use_card_text_clipboard';

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
  childrenContainerRef: RefObject<HTMLDivElement | null>;
  childrenClassName?: string;
  actions: CardAction[];
  children: ReactNode;
}

export const CardBase = ({
  id,
  childrenContainerRef,
  childrenClassName,
  isLoading,
  selection,
  actions,
  children,
}: CardProps) => {
  useCardClearTextSelection(childrenContainerRef, id);

  useCardTextClipboard(childrenContainerRef);

  const startDragging = useCardDragHandle(id);

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
        className={mergeClassNames(s['children-container'], childrenClassName)}
        // TLDraw captures all wheel events; walk from the event target up to
        // this container — if any element in the chain is scrollable, reserve
        // the wheel event for it instead of letting tldraw zoom/pan.
        onWheelCapture={(event) => {
          let el = event.target as HTMLElement | null;
          while (el && el !== event.currentTarget.parentElement) {
            const style = window.getComputedStyle(el);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
              if (el.scrollHeight > el.clientHeight) {
                event.stopPropagation();
                return;
              }
            }
            el = el.parentElement;
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
