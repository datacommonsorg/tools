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
import * as instanceConfig from '@/src/config/instance_config';
import {
  DEFAULT_INSTANCE_CONFIG,
  resetInstanceConfigForTests,
} from '@/src/config/instance_config';
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
  vi.restoreAllMocks();
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
    // Expectation: A "Primary" navigation landmark hidden below `lg` renders both
    //              links in order, marks only the active route link with
    //              `aria-current="page"` and active styling, and applies hover
    //              styling to the inactive link.
    writeSlot({
      navigation: [
        { label: 'Explore', href: '#/agent' },
        { label: 'Dashboards', href: '#/metrics' },
      ],
    });
    renderHeader();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(nav.classList.contains('hidden')).toBe(true);
    expect(nav.classList.contains('lg:flex')).toBe(true);
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'Explore',
      'Dashboards',
    ]);
    expect(links[0].getAttribute('aria-current')).toBe('page');
    expect(links[0].classList.contains('text-nav-active')).toBe(true);
    expect(links[0].classList.contains('hover:text-on-surface')).toBe(false);
    expect(links[1].getAttribute('aria-current')).toBeNull();
    expect(links[1].classList.contains('hover:text-on-surface')).toBe(true);
    expect(links[1].classList.contains('text-nav-active')).toBe(false);
  });

  it('opens every navigation link in the current tab', () => {
    // Test: Tab behavior of header navigation links.
    // Situation: The theme document declares a hash route, a root-relative
    //            path, and an https URL.
    // Expectation: Every link has target="_self", and only the https link
    //              carries rel="noopener noreferrer".
    writeSlot({
      navigation: [
        { label: 'Dashboards', href: '#/metrics' },
        { label: 'Download', href: '/download' },
        { label: 'Docs', href: 'https://docs.datacommons.org/' },
      ],
    });
    renderHeader();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
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
  });

  it.each([
    ['javascript:', 'javascript:alert(1)'],
    ['data:', 'data:text/html,x'],
    ['vbscript:', 'vbscript:msgbox(1)'],
    ['relative', 'relative/path'],
  ])('renders a %s navigation href as an unstyled fallback span', (_, href) => {
    // Test: Header navigation entry with an unsafe href.
    // Situation: The instance configuration is stubbed so that a navigation
    //            entry carries a script, data, or relative URL, which
    //            `getInstanceConfig` would otherwise discard.
    // Expectation: The entry renders its label on an unstyled fallback span
    //              with no link role and no class attribute.
    vi.spyOn(instanceConfig, 'getInstanceConfig').mockReturnValue({
      ...DEFAULT_INSTANCE_CONFIG,
      navigation: [{ label: 'Evil', href }],
    });
    renderHeader();
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(within(nav).queryByRole('link')).toBeNull();
    const fallback = within(nav).getByText('Evil');
    expect(fallback.tagName).toBe('SPAN');
    expect(fallback.getAttribute('class')).toBeNull();
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
