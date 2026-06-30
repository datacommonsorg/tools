'use client';

import type {
  ComponentPropsWithRef,
  ComponentType,
  PointerEvent,
  ReactNode,
  Ref,
} from 'react';
import { Button } from '~/components/elements/button';
import { useCachedResizeValues } from '~/hooks/use_cached_resize_values';
import s from './base.module.scss';

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
}

interface CardProps extends CardState {
  contentContainerRef: Ref<HTMLDivElement>;
  actions: CardAction[];
  content: ReactNode;

  /** **Note**: This isn't shown while `isLoading`. */
  footer?: ReactNode;

  /**
   * Press handler for the actions bar, which doubles as the card's drag handle.
   * The bar sits outside the shape's geometry, so the canvas can't drag it
   * natively — the shape wires this up to move itself instead.
   */
  onActionsPointerDown?: (event: PointerEvent<HTMLDivElement>) => void;
}

export const CardBase = ({
  contentContainerRef,
  isLoading,
  selection,
  actions,
  content,
  footer,
  onActionsPointerDown,
}: CardProps) => {
  const getCachedCanScroll = useCachedResizeValues((element: HTMLElement) => {
    return element.scrollHeight > element.clientHeight;
  });

  return (
    <article
      className={s.container}
      data-is-loading={isLoading}
      data-selection={selection}
    >
      <div
        className={s['actions-container']}
        onPointerDown={onActionsPointerDown}
      >
        {actions.map((action, index) => (
          <Button
            key={index}
            icon={action.icon}
            size="medium"
            variant="flat"
            tone="card-action"
            aria-label={action.label}
            // Prevent tldraw from triggering canvas gestures (e.g. dragging)
            onPointerDown={(event) => event.stopPropagation()}
            onClick={action.onClick}
            isDisabled={action.isDisabled}
          />
        ))}
      </div>

      <div
        ref={contentContainerRef}
        className={s['content-container']}
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
        <div className={s.content}>{content}</div>
        <div className={s.footer} inert={isLoading}>
          {footer}
        </div>
      </div>
    </article>
  );
};
