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
 * debug drawer, implementing roving `tabIndex` and automatic keyboard tab
 * activation.
 */

import { type KeyboardEvent, useRef } from 'react';

const TAB_LIST_CLASSES =
  'flex items-center gap-1 overflow-x-auto no-scrollbar border-b border-outline pb-2';
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
 * minimum touch targets, optional count/status badges, and automatic activation
 * on `ArrowRight`, `ArrowLeft`, `Home`, and `End`.
 */
export const DebugTabs = <T extends string = string>({
  idPrefix,
  ariaLabel,
  tabs,
  activeTabId,
  onSelectTab,
}: DebugTabsProps<T>) => {
  const tabButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);

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

  return (
    <div role="tablist" aria-label={ariaLabel} className={TAB_LIST_CLASSES}>
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
  );
};
