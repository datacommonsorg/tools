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
 * `0`), click selection, and automatic keyboard activation.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  type DebugTabItem,
  DebugTabs,
  getDebugTabElementId,
  getDebugTabPanelElementId,
} from '@/src/components/panel_debug/tabs_debug';

type SampleTabId = 'overview' | 'trajectory' | 'response' | 'timing';

const SAMPLE_TABS: readonly DebugTabItem<SampleTabId>[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'trajectory', label: 'Trajectory', badge: 0 },
  { id: 'response', label: 'Response', badge: 3 },
  { id: 'timing', label: 'Timing', badge: '365ms' },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
});
