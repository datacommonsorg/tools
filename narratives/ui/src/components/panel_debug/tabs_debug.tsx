/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Accessible WAI-ARIA `tablist` navigation primitive for the turn
 * debug drawer, implementing roving `tabIndex`, automatic keyboard tab
 * activation, and horizontal overflow scroll controls.
 */

import { useReducedMotion } from 'motion/react';
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { ChevronDownIcon } from '@/src/components/icons';
import { DEBUG_PANEL_COPY } from '@/src/components/panel_debug/copy_debug';

const MIN_SCROLL_STEP_PX = 120;
const VIEWPORT_SCROLL_FRACTION = 0.75;
const SCROLL_END_TOLERANCE_PX = 1;
/** Pixels per line for wheel events that report `DOM_DELTA_LINE`. */
const WHEEL_LINE_HEIGHT_PX = 16;

const TAB_STRIP_CLASSES =
  'flex items-center gap-1 border-b border-outline pb-2';
const TAB_LIST_CLASSES =
  'flex-1 min-w-0 flex items-center gap-1 overflow-x-auto thin-scrollbar';
const SCROLL_BUTTON_CLASSES =
  'w-11 h-11 shrink-0 flex items-center justify-center rounded-full text-on-surface-variant hover:bg-button-hover hover:text-on-surface focus-visible:-outline-offset-2 motion-safe:transition-colors disabled:opacity-30 disabled:pointer-events-none';
const TAB_BASE_CLASSES =
  'min-h-11 min-w-11 shrink-0 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-full border text-label-large whitespace-nowrap focus-visible:-outline-offset-2 motion-safe:transition-colors';
const TAB_ACTIVE_CLASSES =
  'border-theme-primary bg-theme-container text-on-theme-container';
const TAB_INACTIVE_CLASSES =
  'border-transparent text-on-surface-variant hover:bg-button-hover hover:text-on-surface';
const BADGE_BASE_CLASSES =
  'inline-flex items-center justify-center rounded-full px-1.5 py-0.5 text-label-small';
const BADGE_ACTIVE_CLASSES = 'bg-surface text-on-theme-container';
const BADGE_INACTIVE_CLASSES = 'bg-surface-muted text-on-surface-variant';

/** Resolves the target tab index for a WAI-ARIA horizontal `tablist` key press. */
const resolveNextTabIndex = (
  key: string,
  currentIndex: number,
  tabCount: number,
): number | null => {
  if (key === 'ArrowRight') {
    return (currentIndex + 1) % tabCount;
  }
  if (key === 'ArrowLeft') {
    return (currentIndex - 1 + tabCount) % tabCount;
  }
  if (key === 'Home') {
    return 0;
  }
  if (key === 'End') {
    return tabCount - 1;
  }
  return null;
};

/**
 * Converts a wheel delta to pixels: line deltas are multiplied by
 * `WHEEL_LINE_HEIGHT_PX`, page deltas by `pageSizePx`, and pixel deltas are
 * returned unchanged.
 */
export const normalizeWheelDeltaPx = (
  delta: number,
  deltaMode: number,
  pageSizePx: number,
): number => {
  if (deltaMode === WheelEvent.DOM_DELTA_LINE) {
    return delta * WHEEL_LINE_HEIGHT_PX;
  }
  if (deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    return delta * pageSizePx;
  }
  return delta;
};

/** Builds the DOM `id` of a `<button role="tab">` rendered by {@link DebugTabs}. */
export const getDebugTabElementId = (idPrefix: string, tabId: string): string =>
  `${idPrefix}-tab-${tabId}`;

/**
 * Builds the DOM `id` of the `<div role="tabpanel">` controlled by `tabId` in
 * {@link DebugTabs}.
 */
export const getDebugTabPanelElementId = (
  idPrefix: string,
  tabId: string,
): string => `${idPrefix}-tabpanel-${tabId}`;

/** Descriptor for one tab button rendered by {@link DebugTabs}. */
export interface DebugTabItem<T extends string = string> {
  id: T;
  label: string;
  /** Optional count or status chip rendered whenever defined, including numeric `0`. */
  badge?: string | number;
}

/** Props for {@link DebugTabs}. */
export interface DebugTabsProps<T extends string = string> {
  /** Shared non-empty prefix pairing each `tab` `id` / `aria-controls` with its `tabpanel`. */
  idPrefix: string;
  ariaLabel: string;
  tabs: readonly DebugTabItem<T>[];
  activeTabId: T;
  onSelectTab: (tabId: T) => void;
}

/**
 * Renders a horizontal WAI-ARIA `tablist` with roving `tabIndex`, 44x44px
 * minimum touch targets, optional count/status badges, horizontal overflow
 * scroll buttons, and automatic activation on `ArrowRight`, `ArrowLeft`,
 * `Home`, and `End`.
 */
export const DebugTabs = <T extends string = string>({
  idPrefix,
  ariaLabel,
  tabs,
  activeTabId,
  onSelectTab,
}: DebugTabsProps<T>) => {
  const shouldReduceMotion = Boolean(useReducedMotion());
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const tabListRef = useRef<HTMLDivElement>(null);
  const tabButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const prevActiveTabIdRef = useRef<T>(activeTabId);

  const updateScrollState = useCallback(() => {
    const element = tabListRef.current;
    if (!element?.isConnected) {
      return;
    }
    const { scrollLeft, clientWidth, scrollWidth } = element;
    const nextCanScrollLeft = scrollLeft > 0;
    const nextCanScrollRight =
      scrollLeft + clientWidth < scrollWidth - SCROLL_END_TOLERANCE_PX;
    setCanScrollLeft((prev) =>
      prev === nextCanScrollLeft ? prev : nextCanScrollLeft,
    );
    setCanScrollRight((prev) =>
      prev === nextCanScrollRight ? prev : nextCanScrollRight,
    );
  }, []);

  // Re-evaluate overflow bounds when the tab descriptors change or the strip resizes.
  useEffect(() => {
    tabButtonRefs.current.length = tabs.length;
    updateScrollState();
    const element = tabListRef.current;
    if (!element || typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(() => {
      updateScrollState();
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [tabs, updateScrollState]);

  // React registers JSX onWheel listeners as passive, so attach a non-passive
  // DOM listener on the tablist to translate vertical wheel deltas horizontally.
  useEffect(() => {
    const element = tabListRef.current;
    if (!element) {
      return;
    }
    const handleWheel = (event: WheelEvent): void => {
      if (
        event.deltaY !== 0 &&
        event.deltaX === 0 &&
        element.scrollWidth > element.clientWidth
      ) {
        // Normalize so the scroll distance does not depend on which unit the
        // browser reports the wheel delta in.
        element.scrollLeft += normalizeWheelDeltaPx(
          event.deltaY,
          event.deltaMode,
          element.clientWidth,
        );
        event.preventDefault();
        updateScrollState();
      }
    };
    element.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      element.removeEventListener('wheel', handleWheel);
    };
  }, [updateScrollState]);

  useEffect(() => {
    if (prevActiveTabIdRef.current === activeTabId) {
      return;
    }
    prevActiveTabIdRef.current = activeTabId;
    const activeIndex = tabs.findIndex((tab) => tab.id === activeTabId);
    if (activeIndex < 0) {
      return;
    }
    const activeElement = tabButtonRefs.current[activeIndex];
    if (
      activeElement?.isConnected &&
      typeof activeElement.scrollIntoView === 'function'
    ) {
      activeElement.scrollIntoView({
        block: 'nearest',
        inline: 'nearest',
        behavior: shouldReduceMotion ? 'auto' : 'smooth',
      });
    }
  }, [activeTabId, shouldReduceMotion, tabs]);

  const scrollTabsByDirection = (direction: -1 | 1): void => {
    const element = tabListRef.current;
    if (!element?.isConnected) {
      return;
    }
    const stepPx = Math.max(
      MIN_SCROLL_STEP_PX,
      Math.round(element.clientWidth * VIEWPORT_SCROLL_FRACTION),
    );
    const left = direction * stepPx;
    if (typeof element.scrollBy === 'function') {
      element.scrollBy({
        left,
        behavior: shouldReduceMotion ? 'auto' : 'smooth',
      });
    } else {
      element.scrollLeft += left;
      updateScrollState();
    }
  };

  const handleTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ): void => {
    if (event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }
    const nextIndex = resolveNextTabIndex(event.key, currentIndex, tabs.length);
    if (nextIndex === null) {
      return;
    }
    event.preventDefault();
    onSelectTab(tabs[nextIndex].id);
    tabButtonRefs.current[nextIndex]?.focus();
  };

  const hasOverflow = canScrollLeft || canScrollRight;

  return (
    <div className={TAB_STRIP_CLASSES}>
      {hasOverflow && (
        <button
          type="button"
          aria-label={DEBUG_PANEL_COPY.scrollTabsLeftLabel}
          disabled={!canScrollLeft}
          onClick={() => scrollTabsByDirection(-1)}
          className={SCROLL_BUTTON_CLASSES}
        >
          <ChevronDownIcon size="sm" className="rotate-90" />
        </button>
      )}
      <div
        ref={tabListRef}
        role="tablist"
        aria-label={ariaLabel}
        onScroll={updateScrollState}
        className={TAB_LIST_CLASSES}
      >
        {tabs.map((tab, index) => {
          const isActive = tab.id === activeTabId;
          const hasBadge = tab.badge !== undefined;
          const tabClassName = `${TAB_BASE_CLASSES} ${
            isActive ? TAB_ACTIVE_CLASSES : TAB_INACTIVE_CLASSES
          }`;
          const badgeClassName = `${BADGE_BASE_CLASSES} ${
            isActive ? BADGE_ACTIVE_CLASSES : BADGE_INACTIVE_CLASSES
          }`;

          return (
            <button
              key={tab.id}
              ref={(element) => {
                tabButtonRefs.current[index] = element;
              }}
              id={getDebugTabElementId(idPrefix, tab.id)}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={getDebugTabPanelElementId(idPrefix, tab.id)}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onSelectTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
              className={tabClassName}
            >
              <span>{tab.label}</span>
              {hasBadge && (
                <span className={badgeClassName}>
                  <span className="sr-only"> </span>
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {hasOverflow && (
        <button
          type="button"
          aria-label={DEBUG_PANEL_COPY.scrollTabsRightLabel}
          disabled={!canScrollRight}
          onClick={() => scrollTabsByDirection(1)}
          className={SCROLL_BUTTON_CLASSES}
        >
          <ChevronDownIcon size="sm" className="-rotate-90" />
        </button>
      )}
    </div>
  );
};
