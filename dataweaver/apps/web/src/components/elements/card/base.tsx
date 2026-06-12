'use client';

import type { ComponentPropsWithRef, ComponentType, ReactNode } from 'react';
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
  actions: CardAction[];
  content: ReactNode;

  /** **Note**: This isn't shown while `isLoading`. */
  footer?: ReactNode;
}

export const CardBase = ({
  isLoading,
  selection,
  actions,
  content,
  footer,
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
      <div className={s['actions-container']}>
        {actions.map((action, index) => (
          <Button
            key={index}
            icon={action.icon}
            size="medium"
            colorScheme={{
              base: 'transparent',
              'base-hover': 'var(--color-card-base)',
              content: 'var(--color-card-base)',
              'content-hover': 'var(--color-card-base-selected)',
            }}
            aria-label={action.label}
            // Prevent tldraw from triggering canvas gestures (e.g. dragging)
            onPointerDown={(event) => event.stopPropagation()}
            onClick={action.onClick}
            isDisabled={action.isDisabled}
          />
        ))}
      </div>

      <div
        className={s['children-container']}
        // TLDraw captures all wheel events; this ensures that cards can be
        // scrolled when children here can scroll
        onWheelCapture={(event) => {
          if (getCachedCanScroll(false, event.currentTarget)) {
            event.stopPropagation();
          }
        }}
      >
        <div className={s.content}>{content}</div>
        <div className={s.footer} inert={isLoading}>
          {footer}
        </div>
      </div>
    </article>
  );
};
