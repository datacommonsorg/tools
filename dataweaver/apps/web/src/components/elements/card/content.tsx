'use client';

import { type ReactNode, type RefObject, useRef, useState } from 'react';
import s from './content.module.scss';
import { useCachedResizeValues } from './use_cached_resize_values';

interface CardContentProps {
  childrenInnerContainerRef: RefObject<HTMLDivElement | null>;
  title: ReactNode;
  children: ReactNode;
}

/**
 * A titled scroll region that fills its card: the title is pinned to the top
 * while the children scroll beneath it.
 */
export const CardContent = ({
  childrenInnerContainerRef,
  title,
  children,
}: CardContentProps) => {
  const childrenOuterContainerRef = useRef<HTMLDivElement>(null);

  const [hasScrolled, setHasScrolled] = useState(false);

  const getCachedCanScroll = useCachedResizeValues(
    childrenInnerContainerRef,
    (element: HTMLElement) => {
      return element.scrollHeight > element.clientHeight;
    },
  );

  return (
    <div
      className={s.container}
      data-has-scrolled={hasScrolled}
      // TLDraw captures all wheel events; this ensures the content can be
      // scrolled by a wheel gesture anywhere over the card (title included),
      // not just directly over the scroll area
      onWheelCapture={(event) => {
        const container = childrenOuterContainerRef.current;
        if (container && getCachedCanScroll(container)) {
          event.stopPropagation();
        }
      }}
    >
      {title && <header className={s['header-container']}>{title}</header>}

      <div
        ref={childrenOuterContainerRef}
        className={s['children-outer-container']}
        onScroll={(event) => {
          const scrolled = event.currentTarget.scrollTop > 0;
          setHasScrolled(scrolled);
        }}
      >
        <div
          ref={childrenInnerContainerRef}
          className={s['children-inner-container']}
        >
          {children}
        </div>
      </div>
    </div>
  );
};
