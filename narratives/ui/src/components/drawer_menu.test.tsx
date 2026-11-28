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
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  within,
} from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MenuDrawer } from '@/src/components/drawer_menu';
import { Header } from '@/src/components/header';
import * as instanceConfig from '@/src/config/instance_config';
import {
  DEFAULT_INSTANCE_CONFIG,
  resetInstanceConfigForTests,
} from '@/src/config/instance_config';
import { resetRuntimeConfigForTests } from '@/src/config/runtime_config';
import {
  ChatSessionProvider,
  useChatSession,
} from '@/src/hooks/chat_session_context';

const writeSlot = (themeDocument: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(themeDocument);
  document.head.appendChild(slot);
  resetInstanceConfigForTests();
};

const writeRuntimeConfigSlot = (payload: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = 'runtime-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(payload);
  document.head.appendChild(slot);
  resetRuntimeConfigForTests();
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
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.getElementById('instance-config')?.remove();
  document.getElementById('runtime-config')?.remove();
  resetInstanceConfigForTests();
  resetRuntimeConfigForTests();
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
    // Expectation: The "Sections" navigation landmark renders both interactive
    //              links in order with pointer and hover styling, and only the
    //              active route link has `aria-current="page"`.
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
    for (const link of links) {
      expect(link.classList.contains('cursor-pointer')).toBe(true);
      expect(link.classList.contains('hover:bg-surface-soft')).toBe(true);
    }
  });

  it('opens every section link in the current tab and closes the drawer', () => {
    // Test: Tab behavior of the drawer's section links.
    // Situation: The theme document declares a hash route, a root-relative
    //            path, and an https URL, and the user clicks the first link.
    // Expectation: Every link has target="_self", only the https link carries
    //              rel="noopener noreferrer", and the click closes the drawer.
    writeSlot({
      navigation: [
        { label: 'Dashboards', href: '#/metrics' },
        { label: 'Download', href: '/download' },
        { label: 'Docs', href: 'https://docs.datacommons.org/' },
      ],
    });
    renderOpenDrawer();
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('target'))).toEqual([
      '_self',
      '_self',
      '_self',
    ]);
    expect(links.map((link) => link.getAttribute('rel'))).toEqual([
      null,
      null,
      'noopener noreferrer',
    ]);
    fireEvent.click(links[0]);
    expect(screen.queryByRole('complementary', { name: 'Menu' })).toBeNull();
  });

  it.each([
    ['javascript:', 'javascript:alert(1)'],
    ['data:', 'data:text/html,x'],
    ['vbscript:', 'vbscript:msgbox(1)'],
    ['relative', 'relative/path'],
  ])('renders a %s section href as an unstyled fallback span', (_, href) => {
    // Test: Drawer section entry with an unsafe href.
    // Situation: The instance configuration is stubbed so that a navigation
    //            entry carries a script, data, or relative URL, which
    //            `getInstanceConfig` would otherwise discard.
    // Expectation: The entry renders its label inside an unstyled fallback span
    //              with no link role and no class attribute.
    vi.spyOn(instanceConfig, 'getInstanceConfig').mockReturnValue({
      ...DEFAULT_INSTANCE_CONFIG,
      navigation: [{ label: 'Evil', href }],
    });
    renderOpenDrawer();
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    expect(within(nav).queryByRole('link')).toBeNull();
    const row = nav.firstElementChild;
    expect(row?.tagName).toBe('SPAN');
    expect(row?.textContent).toContain('Evil');
    expect(row?.getAttribute('class')).toBeNull();
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

  it('renders the section links without New chat while chat is disabled', () => {
    // Test: The menu drawer while chat is disabled.
    // Situation: #runtime-config holds `enable_chat: false`, the theme
    //   document declares two navigation tabs, and the menu drawer is open.
    // Expectation: The "Sections" navigation renders both links, and New chat
    //   is absent.
    writeRuntimeConfigSlot({ enable_chat: false });
    writeSlot({
      navigation: [
        { label: 'Explore', href: '#/agent' },
        { label: 'Dashboards', href: '#/metrics' },
      ],
    });
    renderOpenDrawer();
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Explore', 'Dashboards']);
    expect(screen.queryByRole('button', { name: 'New chat' })).toBeNull();
  });

  it('clears the conversation and closes when New chat is clicked', async () => {
    // Test: The menu drawer's New chat control.
    // Situation: One question has been asked and the menu drawer is open.
    // Expectation: Clicking New chat leaves no turns and closes the drawer.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: 'OK',
        body: new ReadableStream<Uint8Array>({
          start(controller) {
            controller.close();
          },
        }),
      }),
    );
    const { result } = renderHook(() => useChatSession(), {
      wrapper: ({ children }: PropsWithChildren) => (
        <ChatSessionProvider>
          <Header />
          <MenuDrawer />
          {children}
        </ChatSessionProvider>
      ),
    });
    await act(async () => {
      await result.current.send('What is the population of France?');
    });
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    expect(result.current.turns).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));

    expect(result.current.turns).toEqual([]);
    expect(screen.queryByRole('button', { name: 'Close menu' })).toBeNull();
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
