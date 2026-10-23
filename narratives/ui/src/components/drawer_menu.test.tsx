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
 * @fileoverview Tests for MenuDrawer: section links, chat controls and dismissal.
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
import { MenuDrawer } from './drawer_menu';
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
      <MenuDrawer />
    </ChatSessionProvider>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
};

afterEach(() => {
  cleanup();
  document.getElementById('instance-config')?.remove();
  resetInstanceConfigForTests();
});

describe('MenuDrawer', () => {
  it('renders no section tabs for the built-in configuration', () => {
    // Test: Default Base Data Commons menu drawer.
    // Situation: The instance-config element is absent, so `navigation` is empty,
    //            and the menu drawer is open.
    // Expectation: The drawer renders without a "Sections" navigation landmark.
    renderOpenDrawer();
    expect(screen.getByRole('button', { name: 'Close menu' })).toBeTruthy();
    expect(screen.queryByRole('navigation', { name: 'Sections' })).toBeNull();
  });

  it('renders the instance tabs as section links', () => {
    // Test: Custom navigation tabs in the menu drawer.
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

  it('offers a new chat and no way to reopen an old one', () => {
    // Test: The chat controls in the menu drawer.
    // Situation: The menu drawer is open.
    // Expectation: "New chat" is offered, and nothing lists saved chats,
    //              because chats are not saved.
    renderOpenDrawer();
    expect(screen.getByRole('button', { name: 'New chat' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Chats' })).toBeNull();
    expect(screen.queryByText('Chats')).toBeNull();
  });

  it('closes when Escape is pressed', () => {
    // Test: Keyboard dismissal of the menu drawer.
    // Situation: The menu drawer is open and the user presses Escape.
    // Expectation: The drawer closes and the menu button reports it collapsed.
    renderOpenDrawer();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('complementary', { name: 'Menu' })).toBeNull();
    expect(
      screen
        .getByRole('button', { name: 'Open menu' })
        .getAttribute('aria-expanded'),
    ).toBe('false');
  });

  it('stays open for keys other than Escape', () => {
    // Test: Only Escape dismisses the menu drawer.
    // Situation: The menu drawer is open and the user presses Enter.
    // Expectation: The drawer stays open.
    renderOpenDrawer();
    fireEvent.keyDown(document, { key: 'Enter' });
    expect(screen.getByRole('complementary', { name: 'Menu' })).toBeTruthy();
  });

  it('closes when the dimmed page behind it is clicked', () => {
    // Test: Click-outside dismissal of the menu drawer.
    // Situation: The menu drawer is open and the user clicks the scrim.
    // Expectation: The scrim is not focusable, and clicking it closes the drawer.
    renderOpenDrawer();
    const scrim = screen.getByRole('complementary', {
      name: 'Menu',
    }).previousElementSibling;
    if (!scrim) throw new Error('The open drawer renders no scrim.');
    expect(scrim.matches('button, a[href], [tabindex]')).toBe(false);
    fireEvent.click(scrim);
    expect(screen.queryByRole('complementary', { name: 'Menu' })).toBeNull();
  });
});
