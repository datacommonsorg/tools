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
 * @fileoverview Tests for resolveNavItems.
 */

import { describe, expect, it } from 'vitest';
import { resolveNavItems } from './nav_config';

describe('resolveNavItems', () => {
  it('removes the header menu entirely for an empty array', () => {
    // Test: Empty navigation array.
    // Situation: `resolveNavItems` is called with an empty array.
    // Expectation: An empty array is returned so no header tabs are rendered.
    expect(resolveNavItems([])).toEqual([]);
  });

  it("maps the instance's entries onto header tabs", () => {
    // Test: Populated navigation array.
    // Situation: Two navigation entries with labels and hash hrefs are provided.
    // Expectation: Each entry is mapped to a `NavItem` with a route identifier
    //              derived from its href.
    const items = resolveNavItems([
      { label: 'Explore', href: '#/agent' },
      { label: 'Dashboards', href: '#/metrics' },
    ]);
    expect(items).toEqual([
      { id: 'agent', label: 'Explore', href: '#/agent' },
      { id: 'metrics', label: 'Dashboards', href: '#/metrics' },
    ]);
  });

  it('derives the route id from the href so the active tab still highlights', () => {
    // Test: Route identifier derivation from hrefs.
    // Situation: Navigation entries use a hash route, a nested hash route, an empty
    //            hash route, the root path, and an external URL with a hash fragment.
    // Expectation: Hash routes resolve to their first segment (or `agent` when empty),
    //              and the root path and external URLs resolve to an empty string.
    expect(resolveNavItems([{ label: 'X', href: '#/statvar' }])[0].id).toBe(
      'statvar',
    );
    expect(
      resolveNavItems([{ label: 'X', href: '#/metrics/extra' }])[0].id,
    ).toBe('metrics');
    expect(resolveNavItems([{ label: 'X', href: '#/' }])[0].id).toBe('agent');
    expect(resolveNavItems([{ label: 'X', href: '/' }])[0].id).toBe('');
    expect(
      resolveNavItems([
        { label: 'Docs', href: 'https://docs.datacommons.org/#agent' },
      ])[0].id,
    ).toBe('');
  });
});
