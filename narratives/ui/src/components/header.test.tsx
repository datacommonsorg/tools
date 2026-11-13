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
 * @fileoverview Tests for Header navigation, wordmark, logo alt text and link,
 * and the menu button.
 */

import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Header } from '@/src/components/header';
import { resetInstanceConfigForTests } from '@/src/config/instance_config';
import { resetRuntimeConfigForTests } from '@/src/config/runtime_config';
import { ChatSessionProvider } from '@/src/hooks/chat_session_context';

const writeSlot = (themeDocument: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(themeDocument);
  document.head.appendChild(slot);
  resetInstanceConfigForTests();
};

const writeChatDisabledSlot = (): void => {
  const slot = document.createElement('script');
  slot.id = 'runtime-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify({ enable_chat: false });
  document.head.appendChild(slot);
  resetRuntimeConfigForTests();
};

const renderHeader = () =>
  render(
    <ChatSessionProvider>
      <Header />
    </ChatSessionProvider>,
  );

const getLogoAlt = (container: HTMLElement): string | null =>
  container.querySelector('img')?.getAttribute('alt') ?? null;

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
  document.getElementById('instance-config')?.remove();
  document.getElementById('runtime-config')?.remove();
  resetInstanceConfigForTests();
  resetRuntimeConfigForTests();
});

describe('Header', () => {
  it('renders no navigation landmark for the built-in configuration', () => {
    // Test: Default Base Data Commons header.
    // Situation: The instance-config element is absent, so `navigation` is empty
    //            and the wordmark is "Data Commons by Google".
    // Expectation: No navigation landmark is rendered, the menu button and wordmark
    //              are rendered, and the logo image has an empty `alt` attribute.
    const { container } = renderHeader();
    expect(screen.queryByRole('navigation')).toBeNull();
    expect(screen.getByRole('button', { name: 'Open menu' })).toBeTruthy();
    expect(screen.getByText('Data Commons by Google')).toBeTruthy();
    expect(getLogoAlt(container)).toBe('');
  });

  it('renders the instance tabs in a labeled navigation landmark', () => {
    // Test: Custom header navigation tabs.
    // Situation: The theme document declares two navigation tabs and the current
    //            hash route is empty (which maps to the `agent` route).
    // Expectation: A "Primary" navigation landmark renders both links in order, and
    //              only the active route link has `aria-current="page"`.
    writeSlot({
      navigation: [
        { label: 'Explore', href: '#/agent' },
        { label: 'Dashboards', href: '#/metrics' },
      ],
    });
    renderHeader();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'Explore',
      'Dashboards',
    ]);
    expect(links[0].getAttribute('aria-current')).toBe('page');
    expect(links[1].getAttribute('aria-current')).toBeNull();
  });

  it.each([
    ['under a base path by default', '/labs/discover/', {}, '/'],
    [
      'under a base path to logo_href',
      '/labs/discover/',
      { logo_href: '/explore' },
      '/explore',
    ],
    [
      'at the root to an http(s) logo_href',
      '/',
      { logo_href: 'https://acme.example/' },
      'https://acme.example/',
    ],
  ])('links the logo %s', (_, pathname, themeDocument, expectedHref) => {
    // Test: Header logo link target.
    // Situation: The app is served under a base path with the default or a
    //            same-origin `logo_href`, or at the root with an http(s)
    //            `logo_href`.
    // Expectation: The logo and wordmark link to the target in the same tab.
    vi.stubGlobal('location', new URL(`https://datacommons.org${pathname}`));
    writeSlot(themeDocument);
    renderHeader();
    const logoLink = screen.getByRole('link', {
      name: 'Data Commons by Google',
    });
    expect(logoLink.getAttribute('href')).toBe(expectedHref);
    expect(logoLink.getAttribute('target')).toBe('_self');
  });

  it.each([
    ['by default', {}],
    ['with a same-origin logo_href', { logo_href: '/explore' }],
  ])('renders a plain logo at the root %s', (_, themeDocument) => {
    // Test: Logo link guard when the app is served at the site root.
    // Situation: The app is at `/`, and `logo_href` is omitted or same-origin,
    //            so following it would reload the app.
    // Expectation: The logo and wordmark render without a link.
    vi.stubGlobal('location', new URL('https://datacommons.org/'));
    writeSlot(themeDocument);
    renderHeader();
    expect(screen.getByText('Data Commons by Google').closest('a')).toBeNull();
  });

  it('hides the wordmark when the theme document omits logo_text', () => {
    // Test: Custom logo without a wordmark.
    // Situation: The theme document omits `logo_text` and sets `logo_alt`.
    // Expectation: No wordmark is rendered, and the logo image uses the configured
    //              alternative text.
    writeSlot({ logo_alt: 'Acme Data Commons logo', instance_name: 'Acme' });
    const { container } = renderHeader();
    expect(screen.queryByText('Data Commons')).toBeNull();
    expect(getLogoAlt(container)).toBe('Acme Data Commons logo');
  });

  it.each([
    ['omits logo_alt', { instance_name: 'Acme' }],
    [
      'sets logo_alt to an empty string',
      { logo_alt: '', instance_name: 'Acme' },
    ],
  ])('derives the alt text from the instance name when the document %s', (_, themeDocument) => {
    // Test: Fallback logo alternative text when `logo_text` and `logo_alt` are
    //       omitted or empty.
    // Situation: The theme document omits `logo_text`, either omits `logo_alt` or
    //            sets it to an empty string, and sets `instance_name` to "Acme".
    // Expectation: The logo alternative text is derived from the instance name.
    writeSlot(themeDocument);
    const { container } = renderHeader();
    expect(getLogoAlt(container)).toBe('Acme logo');
  });

  it('omits the menu button when chat is disabled and there are no tabs', () => {
    // Test: Header while chat is disabled on the built-in configuration.
    // Situation: #runtime-config holds `enable_chat: false` and `navigation`
    //   is empty, so the drawer would hold no item.
    // Expectation: The logo and wordmark render, and the menu button does not.
    writeChatDisabledSlot();
    const { container } = renderHeader();
    expect(container.querySelector('img')).not.toBeNull();
    expect(screen.getByText('Data Commons by Google')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Open menu' })).toBeNull();
  });

  it('keeps the tabs and the menu button when chat is disabled and tabs exist', () => {
    // Test: Header while chat is disabled on an instance with tabs.
    // Situation: #runtime-config holds `enable_chat: false` and the theme
    //   document declares two navigation tabs.
    // Expectation: The "Primary" navigation landmark and the menu button
    //   render.
    writeChatDisabledSlot();
    writeSlot({
      navigation: [
        { label: 'Explore', href: '#/agent' },
        { label: 'Dashboards', href: '#/metrics' },
      ],
    });
    renderHeader();
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Open menu' })).toBeTruthy();
  });
});
