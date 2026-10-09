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
 * @fileoverview Tests for MetricsPage empty state and tab switching.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { resetInstanceConfigForTests } from '@/src/config/instance_config';
import { MetricsPage } from './metrics_page';

const writeSlot = (themeDocument: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(themeDocument);
  document.head.appendChild(slot);
  resetInstanceConfigForTests();
};

afterEach(() => {
  cleanup();
  document.getElementById('instance-config')?.remove();
  resetInstanceConfigForTests();
});

describe('MetricsPage', () => {
  it('renders the empty state for the built-in configuration', () => {
    // Test: Default Base Data Commons metrics page.
    // Situation: The instance-config element is absent, so `metrics.tabs` is empty.
    // Expectation: The page heading and empty-state message render without a tab
    //              list or subtitle.
    render(<MetricsPage />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Key Metrics',
    );
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(
      'No metrics configured',
    );
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(
      screen.getByText('No dashboards are configured for this instance.'),
    ).toBeTruthy();
    expect(screen.queryByText(/powered by Data Commons/)).toBeNull();
  });

  it('renders the instance tabs and switches between them', () => {
    // Test: Custom metrics tabs and tile remounting on tab switch.
    // Situation: The theme document configures two tabs with different tile types
    //            (`highlight` and `line`) and sets `instance_name` to "Acme".
    // Expectation: Both tabs render with the first tab selected and its highlight
    //              tile mounted; clicking the second tab selects it and replaces
    //              the highlight tile with the line tile.
    writeSlot({
      instance_name: 'Acme',
      metrics: {
        tabs: [
          {
            id: 'health',
            label: 'Health',
            tiles: [{ type: 'highlight', title: 'Life expectancy' }],
          },
          {
            id: 'economy',
            label: 'Economy',
            tiles: [{ type: 'line', title: 'GDP over time' }],
          },
        ],
      },
    });
    const { container } = render(<MetricsPage />);
    const tablist = screen.getByRole('tablist', { name: 'Metrics categories' });
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Health', 'Economy']);
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect(tabs[1].getAttribute('aria-selected')).toBe('false');
    expect(screen.getByText(/Acme dashboards/)).toBeTruthy();
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
    expect(container.querySelector('datacommons-highlight')).not.toBeNull();
    expect(container.querySelector('datacommons-line')).toBeNull();

    fireEvent.click(tabs[1]);
    expect(tabs[0].getAttribute('aria-selected')).toBe('false');
    expect(tabs[1].getAttribute('aria-selected')).toBe('true');
    expect(container.querySelector('datacommons-highlight')).toBeNull();
    expect(container.querySelector('datacommons-line')).not.toBeNull();
  });
});
