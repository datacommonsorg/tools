'use client';

import { type ReactNode, type RefObject, useRef, useState } from 'react';
import { useCachedResizeValues } from '~/hooks/use_cached_resize_values';
import s from './content.module.scss';

interface CardContentProps {
  contentContainerRef: RefObject<HTMLDivElement | null>;
  title: ReactNode;
  children: ReactNode;
}

/**
 * A titled scroll region that fills its card: the title is pinned to the top
 * while the children scroll beneath it.
 */
export const CardContent = ({
  contentContainerRef,
  title,
  children,
}: CardContentProps) => {
  const contentOuterContainerRef = useRef<HTMLDivElement>(null);

  const [hasScrolled, setHasScrolled] = useState(false);

  const getCachedCanScroll = useCachedResizeValues((element: HTMLElement) => {
    return element.scrollHeight > element.clientHeight;
  });

  return (
    <div
      className={s.container}
      data-has-scrolled={hasScrolled}
      // TLDraw captures all wheel events; this ensures the content can be
      // scrolled by a wheel gesture anywhere over the card (title included),
      // not just directly over the scroll area
      onWheelCapture={(event) => {
        const content = contentOuterContainerRef.current;
        if (content && getCachedCanScroll(false, content)) {
          event.stopPropagation();
        }
      }}
    >
      {title && <header className={s['header-container']}>{title}</header>}

      <div
        ref={contentOuterContainerRef}
        className={s['content-outer-container']}
        onScroll={(event) => {
          const scrolled = event.currentTarget.scrollTop > 0;
          setHasScrolled(scrolled);
        }}
      >
        <div ref={contentContainerRef} className={s['content-inner-container']}>
          {children}
        </div>
      </div>
    </div>
  );
};
