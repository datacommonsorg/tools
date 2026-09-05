'use client';

import type {
  ComponentPropsWithRef,
  ComponentType,
  ReactNode,
  RefObject,
} from 'react';
import { type TLShapeId, useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconDragIndicator } from '~/components/primitives/icons/drag_indicator';
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
  allowOverflow?: boolean;
  actions: CardAction[];
  children: ReactNode;
}

export const CardBase = ({
  id,
  childrenContainerRef,
  allowOverflow,
  isLoading,
  selection,
  actions,
  children,
}: CardProps) => {
  useCardClearTextSelection(childrenContainerRef, id);

  useCardTextClipboard(childrenContainerRef);

  const editor = useEditor();

  const startDragging = useCardDragHandle(id);

  return (
    <article
      className={s.container}
      data-is-loading={isLoading}
      data-selection={selection}
      // Unselected: a pointerdown here would otherwise fall through to
      // tldraw's default select tool, which selects AND starts dragging in
      // one gesture. Select the card ourselves and swallow the event so the
      // first press only selects — dragging then happens via the actions
      // bar. Skip for non-select tools (e.g. hand, which should pan) and
      // modifier-held clicks (so native shift/ctrl/cmd multi-select and
      // alt-drag-to-duplicate work).
      onPointerDown={
        selection === 'none'
          ? (event) => {
              if (event.button !== 0) return;
              if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
              if (editor.getCurrentToolId() !== 'select') return;
              event.stopPropagation();
              editor.select(id);
            }
          : undefined
      }
    >
      <div
        className={s['actions-container']}
        onPointerDown={selection !== 'none' ? startDragging : undefined}
      >
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
        <IconDragIndicator className={s['icon-drag-indicator']} />
      </div>

      <div
        ref={childrenContainerRef}
        className={s['children-container']}
        data-allow-overflow={allowOverflow ?? false}
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
        // stays selectable/highlightable. While multi-selected we let events
        // through so tldraw keeps handling multi-select/drag; while
        // unselected we also let them through, for the cases the article's
        // own pointerdown handler doesn't cover (hand tool, modifier-click)
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
