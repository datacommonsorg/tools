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
 * @fileoverview Unit tests for `DebugTabs`: WAI-ARIA `tablist` / `tab`
 * semantics, element ID pairing, roving `tabIndex`, badge rendering (including
 * `0`), click selection, automatic keyboard activation, and horizontal overflow
 * scrolling.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { DEBUG_PANEL_COPY } from '@/src/components/panel_debug/copy_debug';
import {
  type DebugTabItem,
  DebugTabs,
  getDebugTabElementId,
  getDebugTabPanelElementId,
  normalizeWheelDeltaPx,
} from '@/src/components/panel_debug/tabs_debug';

type SampleTabId = 'overview' | 'trajectory' | 'response' | 'timing';

const SAMPLE_TABS: readonly DebugTabItem<SampleTabId>[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'trajectory', label: 'Trajectory', badge: 0 },
  { id: 'response', label: 'Response', badge: 3 },
  { id: 'timing', label: 'Timing', badge: '365ms' },
];

interface ScrollMetrics {
  scrollLeft: number;
  clientWidth: number;
  scrollWidth: number;
}

/** Configures mutable scroll metrics on a DOM element for overflow testing. */
const defineScrollMetrics = (
  element: HTMLElement,
  initial: ScrollMetrics,
): ScrollMetrics => {
  const metrics: ScrollMetrics = { ...initial };
  Object.defineProperty(element, 'scrollLeft', {
    configurable: true,
    get: () => metrics.scrollLeft,
    set: (value: number) => {
      metrics.scrollLeft = value;
    },
  });
  Object.defineProperty(element, 'clientWidth', {
    configurable: true,
    get: () => metrics.clientWidth,
  });
  Object.defineProperty(element, 'scrollWidth', {
    configurable: true,
    get: () => metrics.scrollWidth,
  });
  return metrics;
};

let prefersReducedMotion = false;
const reducedMotionListeners = new Set<() => void>();

const setReducedMotionPreference = (shouldReduce: boolean): void => {
  prefersReducedMotion = shouldReduce;
  for (const listener of reducedMotionListeners) {
    listener();
  }
};

beforeAll(() => {
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return query.includes('prefers-reduced-motion') && prefersReducedMotion;
    },
    media: query,
    addEventListener: (_type: string, listener: () => void) => {
      if (query.includes('prefers-reduced-motion')) {
        reducedMotionListeners.add(listener);
      }
    },
    removeEventListener: (_type: string, listener: () => void) => {
      reducedMotionListeners.delete(listener);
    },
  }));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  if (prefersReducedMotion) {
    setReducedMotionPreference(false);
  }
});

afterAll(() => {
  reducedMotionListeners.clear();
  vi.unstubAllGlobals();
});

describe('DebugTabs', () => {
  it('renders a WAI-ARIA tablist with paired tab and tabpanel IDs and roving tabIndex', () => {
    // Test: ARIA attributes, deterministic ID builders, and roving `tabIndex`.
    // Situation: Four tabs render with `activeTabId="response"` and `idPrefix="turn-0"`.
    // Expectation: The `tablist` exposes its accessible label, each `tab` button
    //   pairs `id` and `aria-controls` via the exported builders, and only the
    //   selected tab has `aria-selected="true"` and `tabIndex={0}`.
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="response"
        onSelectTab={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('tablist', { name: 'Turn debug sections' }),
    ).toBeDefined();

    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(SAMPLE_TABS.length);

    SAMPLE_TABS.forEach((item, index) => {
      const button = tabs[index];
      const isSelected = item.id === 'response';
      expect(button.getAttribute('type')).toBe('button');
      expect(button.getAttribute('id')).toBe(
        getDebugTabElementId('turn-0', item.id),
      );
      expect(button.getAttribute('aria-controls')).toBe(
        getDebugTabPanelElementId('turn-0', item.id),
      );
      expect(button.getAttribute('aria-selected')).toBe(String(isSelected));
      expect(button.tabIndex).toBe(isSelected ? 0 : -1);
    });
  });

  it('renders numeric 0, positive number, and string badges while omitting undefined badges', () => {
    // Test: Badge text rendering including falsy numeric `0` and screen-reader spacing.
    // Situation: `SAMPLE_TABS` provides `undefined` on Overview, `0` on
    //   Trajectory, `3` on Response, and `'365ms'` on Timing.
    // Expectation: Overview exposes only its label text, while Trajectory,
    //   Response, and Timing expose space-separated badge text (`0`, `3`, `365ms`).
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={vi.fn()}
      />,
    );

    const [overviewTab, trajectoryTab, responseTab, timingTab] =
      screen.getAllByRole('tab');
    expect(overviewTab.textContent).toBe('Overview');
    expect(trajectoryTab.textContent).toBe('Trajectory 0');
    expect(responseTab.textContent).toBe('Response 3');
    expect(timingTab.textContent).toBe('Timing 365ms');
  });

  it('invokes onSelectTab when a tab is clicked', () => {
    // Test: Pointer activation of a tab button.
    // Situation: The user clicks the Trajectory tab.
    // Expectation: `onSelectTab` is called once with `'trajectory'`.
    const handleSelectTab = vi.fn();
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={handleSelectTab}
      />,
    );

    fireEvent.click(screen.getByRole('tab', { name: /Trajectory/ }));

    expect(handleSelectTab).toHaveBeenCalledTimes(1);
    expect(handleSelectTab).toHaveBeenCalledWith('trajectory');
  });

  it('navigates with ArrowRight, ArrowLeft, Home, and End (including wraparound) while ignoring modified or unrelated keys', () => {
    // Test: WAI-ARIA horizontal keyboard navigation, wraparound, and key filtering.
    // Situation: `ArrowRight`, `ArrowLeft`, `End`, `Home`, modified arrow keys,
    //   and `Escape` are dispatched on tab buttons.
    // Expectation: Navigation keys call `preventDefault()`, focus the target
    //   tab, and pass its ID to `onSelectTab` with wraparound; modified and
    //   unrelated keys are ignored.
    const handleSelectTab = vi.fn();
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={handleSelectTab}
      />,
    );

    const tabs = screen.getAllByRole('tab');

    expect(fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })).toBe(false);
    expect(handleSelectTab).toHaveBeenNthCalledWith(1, 'trajectory');
    expect(document.activeElement).toBe(tabs[1]);

    expect(fireEvent.keyDown(tabs[3], { key: 'ArrowRight' })).toBe(false);
    expect(handleSelectTab).toHaveBeenNthCalledWith(2, 'overview');
    expect(document.activeElement).toBe(tabs[0]);

    expect(fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' })).toBe(false);
    expect(handleSelectTab).toHaveBeenNthCalledWith(3, 'timing');
    expect(document.activeElement).toBe(tabs[3]);

    expect(fireEvent.keyDown(tabs[2], { key: 'ArrowLeft' })).toBe(false);
    expect(handleSelectTab).toHaveBeenNthCalledWith(4, 'trajectory');
    expect(document.activeElement).toBe(tabs[1]);

    expect(fireEvent.keyDown(tabs[1], { key: 'End' })).toBe(false);
    expect(handleSelectTab).toHaveBeenNthCalledWith(5, 'timing');
    expect(document.activeElement).toBe(tabs[3]);

    expect(fireEvent.keyDown(tabs[3], { key: 'Home' })).toBe(false);
    expect(handleSelectTab).toHaveBeenNthCalledWith(6, 'overview');
    expect(document.activeElement).toBe(tabs[0]);

    expect(
      fireEvent.keyDown(tabs[0], { key: 'ArrowRight', ctrlKey: true }),
    ).toBe(true);
    expect(fireEvent.keyDown(tabs[0], { key: 'ArrowLeft', altKey: true })).toBe(
      true,
    );
    expect(fireEvent.keyDown(tabs[0], { key: 'Home', metaKey: true })).toBe(
      true,
    );
    expect(fireEvent.keyDown(tabs[0], { key: 'Escape' })).toBe(true);
    expect(handleSelectTab).toHaveBeenCalledTimes(6);
  });

  it('shows overflow scroll buttons outside tablist and updates disabled state at boundaries', () => {
    // Test: Overflow scroll button visibility, ARIA containment, and boundary disabling.
    // Situation: Tablist starts without overflow, then overflows and scrolls from left edge to middle to right edge.
    // Expectation: Scroll buttons stay hidden without overflow; when overflowing they render outside `role="tablist"`
    //   and toggle `disabled` accurately at `scrollLeft === 0` and at the right boundary.
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={vi.fn()}
      />,
    );

    const tablist = screen.getByRole('tablist', {
      name: 'Turn debug sections',
    });
    expect(tablist.classList.contains('thin-scrollbar')).toBe(true);
    expect(tablist.classList.contains('no-scrollbar')).toBe(false);
    expect(
      screen.queryByRole('button', {
        name: DEBUG_PANEL_COPY.scrollTabsLeftLabel,
      }),
    ).toBeNull();
    expect(
      screen.queryByRole('button', {
        name: DEBUG_PANEL_COPY.scrollTabsRightLabel,
      }),
    ).toBeNull();

    const metrics = defineScrollMetrics(tablist, {
      scrollLeft: 0,
      clientWidth: 240,
      scrollWidth: 600,
    });
    fireEvent.scroll(tablist);

    const leftButton = screen.getByRole('button', {
      name: DEBUG_PANEL_COPY.scrollTabsLeftLabel,
    }) as HTMLButtonElement;
    const rightButton = screen.getByRole('button', {
      name: DEBUG_PANEL_COPY.scrollTabsRightLabel,
    }) as HTMLButtonElement;

    expect(tablist.contains(leftButton)).toBe(false);
    expect(tablist.contains(rightButton)).toBe(false);
    expect([...leftButton.classList]).toEqual(
      expect.arrayContaining(['w-11', 'h-11']),
    );
    expect(leftButton.disabled).toBe(true);
    expect(rightButton.disabled).toBe(false);

    metrics.scrollLeft = 180;
    fireEvent.scroll(tablist);
    expect(leftButton.disabled).toBe(false);
    expect(rightButton.disabled).toBe(false);

    metrics.scrollLeft = 360;
    fireEvent.scroll(tablist);
    expect(leftButton.disabled).toBe(false);
    expect(rightButton.disabled).toBe(true);
  });

  it('scrolls by 75% of clientWidth when clicking left and right scroll buttons and honors reduced motion', () => {
    // Test: Scroll button step calculation and reduced-motion behavior.
    // Situation: Overflowing tablist (`clientWidth = 240`, `scrollLeft = 180`) with `scrollBy` spy.
    // Expectation: Clicking right/left buttons calls `scrollBy` with `±180` (`smooth`), switching to `auto` when reduced motion is enabled.
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={vi.fn()}
      />,
    );

    const tablist = screen.getByRole('tablist');
    defineScrollMetrics(tablist, {
      scrollLeft: 180,
      clientWidth: 240,
      scrollWidth: 600,
    });
    const scrollBySpy = vi.fn();
    tablist.scrollBy = scrollBySpy;
    fireEvent.scroll(tablist);

    const leftButton = screen.getByRole('button', {
      name: DEBUG_PANEL_COPY.scrollTabsLeftLabel,
    });
    const rightButton = screen.getByRole('button', {
      name: DEBUG_PANEL_COPY.scrollTabsRightLabel,
    });

    fireEvent.click(rightButton);
    expect(scrollBySpy).toHaveBeenNthCalledWith(1, {
      left: 180,
      behavior: 'smooth',
    });

    fireEvent.click(leftButton);
    expect(scrollBySpy).toHaveBeenNthCalledWith(2, {
      left: -180,
      behavior: 'smooth',
    });

    cleanup();
    setReducedMotionPreference(true);
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={vi.fn()}
      />,
    );

    const reducedMotionTablist = screen.getByRole('tablist');
    defineScrollMetrics(reducedMotionTablist, {
      scrollLeft: 180,
      clientWidth: 240,
      scrollWidth: 600,
    });
    reducedMotionTablist.scrollBy = scrollBySpy;
    fireEvent.scroll(reducedMotionTablist);

    fireEvent.click(
      screen.getByRole('button', {
        name: DEBUG_PANEL_COPY.scrollTabsRightLabel,
      }),
    );
    expect(scrollBySpy).toHaveBeenNthCalledWith(3, {
      left: 180,
      behavior: 'auto',
    });
  });

  it('calls scrollIntoView on the newly active tab after mount without scrolling on initial render', () => {
    // Test: Active tab visibility synchronization on `activeTabId` changes.
    // Situation: `DebugTabs` mounts with `activeTabId="overview"` and then rerenders with `activeTabId="timing"`.
    // Expectation: `scrollIntoView` is not called on mount, and is called once on the Timing tab when selected.
    const scrollIntoViewSpy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: scrollIntoViewSpy,
    });

    const { rerender } = render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={vi.fn()}
      />,
    );

    expect(scrollIntoViewSpy).not.toHaveBeenCalled();

    rerender(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="timing"
        onSelectTab={vi.fn()}
      />,
    );

    expect(scrollIntoViewSpy).toHaveBeenCalledTimes(1);
    expect(scrollIntoViewSpy).toHaveBeenCalledWith({
      block: 'nearest',
      inline: 'nearest',
      behavior: 'smooth',
    });
    expect(scrollIntoViewSpy.mock.instances[0]).toBe(
      screen.getByRole('tab', { name: /Timing/ }),
    );
  });

  it('translates vertical mouse-wheel deltas into horizontal scrolling when overflowing', () => {
    // Test: Vertical wheel translation on horizontal tablist.
    // Situation: A vertical wheel event (`deltaY = 90, deltaX = 0`) fires on an overflowing tablist, followed by a diagonal event and a non-overflowing event.
    // Expectation: Vertical wheel advances `scrollLeft` and calls `preventDefault()`, while horizontal/non-overflowing wheel events pass through.
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={vi.fn()}
      />,
    );

    const tablist = screen.getByRole('tablist');
    const metrics = defineScrollMetrics(tablist, {
      scrollLeft: 0,
      clientWidth: 240,
      scrollWidth: 600,
    });

    expect(fireEvent.wheel(tablist, { deltaY: 90, deltaX: 0 })).toBe(false);
    expect(metrics.scrollLeft).toBe(90);

    expect(fireEvent.wheel(tablist, { deltaY: 40, deltaX: 25 })).toBe(true);
    expect(metrics.scrollLeft).toBe(90);

    metrics.scrollWidth = 240;
    expect(fireEvent.wheel(tablist, { deltaY: 50, deltaX: 0 })).toBe(true);
    expect(metrics.scrollLeft).toBe(90);
  });

  it('converts line-mode wheel deltas to pixels before scrolling', () => {
    // Test: Line-mode wheel normalization on the tablist.
    // Situation: A vertical wheel event reports `deltaY = 3` in
    //   `DOM_DELTA_LINE` on an overflowing tablist.
    // Expectation: `scrollLeft` advances by 3 lines of 16px (48px) rather
    //   than by 3px.
    render(
      <DebugTabs
        idPrefix="turn-0"
        ariaLabel="Turn debug sections"
        tabs={SAMPLE_TABS}
        activeTabId="overview"
        onSelectTab={vi.fn()}
      />,
    );

    const tablist = screen.getByRole('tablist');
    const metrics = defineScrollMetrics(tablist, {
      scrollLeft: 0,
      clientWidth: 240,
      scrollWidth: 600,
    });

    expect(
      fireEvent.wheel(tablist, {
        deltaY: 3,
        deltaX: 0,
        deltaMode: WheelEvent.DOM_DELTA_LINE,
      }),
    ).toBe(false);
    expect(metrics.scrollLeft).toBe(48);
  });
});

describe('normalizeWheelDeltaPx', () => {
  it.each([
    { mode: 'pixel', deltaMode: 0, delta: 90, expected: 90 },
    { mode: 'line', deltaMode: 1, delta: 3, expected: 48 },
    { mode: 'line (negative)', deltaMode: 1, delta: -2, expected: -32 },
    { mode: 'page', deltaMode: 2, delta: 1, expected: 240 },
  ])('converts a $mode delta to pixels', ({ deltaMode, delta, expected }) => {
    // Test: Wheel delta unit conversion.
    // Situation: A delta in pixel, line, or page mode with a 240px page size.
    // Expectation: Pixels pass through, lines scale by 16px, and pages scale
    //   by the page size.
    expect(normalizeWheelDeltaPx(delta, deltaMode, 240)).toBe(expected);
  });
});
