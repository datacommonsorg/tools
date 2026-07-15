'use client';

import {
  type ReactNode,
  type RefObject,
  useEffect,
  useRef,
  useState,
} from 'react';
import s from './content.module.scss';

/**
 * Minimum vertical overflow (px) before the region is treated as scrollable.
 * Below this the scrollbar is hidden and wheel gestures fall through to TLDraw,
 * so a few clipped pixels don't hijack scrolling or show a stub scrollbar.
 *
 * This matches padding-bottom on the inner container.
 */
const SCROLL_THRESHOLD_PX = 28;

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

  const [canScroll, setCanScroll] = useState(false);
  const [hasScrolled, setHasScrolled] = useState(false);

  useEffect(() => {
    const childrenOuterContainer = childrenOuterContainerRef.current;
    if (!childrenOuterContainer) return;

    const checkIfCanScroll = () => {
      const scrollableArea =
        childrenOuterContainer.scrollHeight -
        childrenOuterContainer.clientHeight;
      setCanScroll(scrollableArea >= SCROLL_THRESHOLD_PX);
    };

    // Sync on mount
    checkIfCanScroll();

    const observer = new ResizeObserver(checkIfCanScroll);
    observer.observe(childrenOuterContainer);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className={s.container}
      data-has-scrolled={hasScrolled}
      // TLDraw captures all wheel events; this ensures the content can be
      // scrolled by a wheel gesture anywhere over the card (title included),
      // not just directly over the scroll area
      onWheelCapture={(event) => {
        if (canScroll) event.stopPropagation();
      }}
    >
      {title && <header className={s['header-container']}>{title}</header>}

      <div
        ref={childrenOuterContainerRef}
        className={s['children-outer-container']}
        data-can-scroll={canScroll}
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
