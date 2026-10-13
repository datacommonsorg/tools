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
 * @fileoverview Tests for SessionDrawer section navigation.
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
import { ChatSessionProvider } from '@/src/hooks/chat_session_context';
import { SessionDrawer } from './drawer_session';
import { Header } from './header';

const writeSlot = (themeDocument: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(themeDocument);
  document.head.appendChild(slot);
  resetInstanceConfigForTests();
};

const renderOpenDrawer = (): void => {
  render(
    <ChatSessionProvider>
      <Header />
      <SessionDrawer />
    </ChatSessionProvider>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
};

afterEach(() => {
  cleanup();
  document.getElementById('instance-config')?.remove();
  resetInstanceConfigForTests();
  window.localStorage.clear();
});

describe('SessionDrawer', () => {
  it('renders no section tabs for the built-in configuration', () => {
    // Test: Default Base Data Commons session drawer.
    // Situation: The instance-config element is absent, so `navigation` is empty,
    //            and the session drawer is open.
    // Expectation: The drawer renders without a "Sections" navigation landmark.
    renderOpenDrawer();
    expect(screen.getByRole('button', { name: 'Close menu' })).toBeTruthy();
    expect(screen.queryByRole('navigation', { name: 'Sections' })).toBeNull();
  });

  it('renders the instance tabs as section links', () => {
    // Test: Custom navigation tabs in the session drawer.
    // Situation: The theme document declares two navigation tabs and the current
    //            hash route is empty (which maps to the `agent` route).
    // Expectation: The "Sections" navigation landmark renders both links in order,
    //              and only the active route link has `aria-current="page"`.
    writeSlot({
      navigation: [
        { label: 'Explore', href: '#/agent' },
        { label: 'Dashboards', href: '#/metrics' },
      ],
    });
    renderOpenDrawer();
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'Explore',
      'Dashboards',
    ]);
    expect(links[0].getAttribute('aria-current')).toBe('page');
    expect(links[1].getAttribute('aria-current')).toBeNull();
  });
});
