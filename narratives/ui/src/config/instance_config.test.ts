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
 * @fileoverview Tests for getInstanceConfig and sanitizeUrl.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_INSTANCE_CONFIG,
  getInstanceConfig,
  resetInstanceConfigForTests,
  sanitizeUrl,
} from './instance_config';

const writeSlot = (text: string): void => {
  document.head.innerHTML = '';
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = text;
  document.head.appendChild(slot);
};

const spyOnWarn = () => vi.spyOn(console, 'warn').mockReturnValue(undefined);

afterEach(() => {
  document.head.innerHTML = '';
  resetInstanceConfigForTests();
  vi.restoreAllMocks();
});

describe('getInstanceConfig', () => {
  it('returns the built-in defaults when the slot is absent', () => {
    // Test: Missing instance-config element.
    // Situation: The document has no element with the id "instance-config".
    // Expectation: The Base Data Commons defaults are returned.
    document.head.innerHTML = '';
    expect(getInstanceConfig()).toEqual(DEFAULT_INSTANCE_CONFIG);
  });

  it('returns the built-in defaults when the slot is empty', () => {
    // Test: Empty instance-config element.
    // Situation: The element exists in the document head but contains only whitespace.
    // Expectation: The Base Data Commons defaults are returned and no warnings are logged.
    const warn = spyOnWarn();
    writeSlot('   ');
    expect(getInstanceConfig()).toEqual(DEFAULT_INSTANCE_CONFIG);
    expect(warn).not.toHaveBeenCalled();
  });

  it('merges a theme document over the defaults', () => {
    // Test: Full theme document.
    // Situation: The element contains a JSON document with snake_case keys and a
    //            nested `splash_assets` object.
    // Expectation: Each key is mapped to its camelCase field, omitted fields keep
    //              their default values, and no warnings are logged.
    const warn = spyOnWarn();
    writeSlot(
      JSON.stringify({
        instance_name: 'Acme Data Commons',
        logo: '/theme/logo-1a2b3c4d.svg',
        logo_text: 'Acme DC',
        logo_alt: 'Acme Data Commons logo',
        splash_assets: {
          thinking_indicator: '/theme/thinking-9f8e7d6c.svg',
          done_indicator: 'https://cdn.example/done.svg',
        },
        headline: 'Explore Acme',
        navigation: [{ label: 'Explore', href: '#/agent' }],
        suggestions: ['How is literacy trending'],
        metrics: {
          tabs: [
            {
              id: 'health',
              label: 'Health',
              tiles: [{ type: 'highlight', title: 'Life expectancy' }],
            },
          ],
        },
      }),
    );
    expect(getInstanceConfig()).toEqual({
      ...DEFAULT_INSTANCE_CONFIG,
      instanceName: 'Acme Data Commons',
      logoUrl: '/theme/logo-1a2b3c4d.svg',
      logoText: 'Acme DC',
      logoAlt: 'Acme Data Commons logo',
      thinkingIndicatorUrl: '/theme/thinking-9f8e7d6c.svg',
      doneIndicatorUrl: 'https://cdn.example/done.svg',
      headline: 'Explore Acme',
      navigation: [{ label: 'Explore', href: '#/agent' }],
      suggestions: ['How is literacy trending'],
      metrics: {
        tabs: [
          {
            id: 'health',
            label: 'Health',
            tiles: [{ type: 'highlight', title: 'Life expectancy' }],
          },
        ],
      },
    });
    expect(getInstanceConfig().tagline).toBe(DEFAULT_INSTANCE_CONFIG.tagline);
    expect(warn).not.toHaveBeenCalled();
  });

  it.each([
    ['omits logo_text and logo_alt', {}],
    [
      'sets logo_text and logo_alt to empty strings',
      { logo_text: '', logo_alt: '' },
    ],
  ])('leaves logoText and logoAlt empty when the document %s', (_, themeDocument) => {
    // Test: Wordmark and logo alt text when `logo_text` and `logo_alt` are omitted
    //       or empty in a theme document.
    // Situation: The element contains a theme document that either omits `logo_text`
    //            and `logo_alt` or sets them to empty strings.
    // Expectation: `logoText` and `logoAlt` resolve to empty strings so a custom
    //              instance does not inherit the "Data Commons" wordmark or alt text.
    writeSlot(JSON.stringify(themeDocument));
    expect(getInstanceConfig().logoText).toBe('');
    expect(getInstanceConfig().logoAlt).toBe('');
  });

  it('keeps the default for a field of the wrong shape and reports it', () => {
    // Test: Invalid field types in the theme document.
    // Situation: `suggestions` is a string, `navigation` contains an entry without
    //            an href, `splash_assets` is a string array, and `metrics.tabs`
    //            contains a null entry.
    // Expectation: Each invalid field falls back to its default value and logs a
    //              warning naming the invalid key.
    const warn = spyOnWarn();
    writeSlot(
      JSON.stringify({
        suggestions: 'not a list',
        navigation: [{ label: 'Missing href' }],
        splash_assets: ['hero.png'],
        metrics: { tabs: [null] },
      }),
    );
    const config = getInstanceConfig();
    expect(config.suggestions).toEqual(DEFAULT_INSTANCE_CONFIG.suggestions);
    expect(config.navigation).toEqual(DEFAULT_INSTANCE_CONFIG.navigation);
    expect(config.thinkingIndicatorUrl).toBe(
      DEFAULT_INSTANCE_CONFIG.thinkingIndicatorUrl,
    );
    expect(config.metrics).toEqual(DEFAULT_INSTANCE_CONFIG.metrics);
    const messages = warn.mock.calls.map((call) => String(call[0]));
    expect(messages).toHaveLength(4);
    for (const key of [
      'suggestions',
      'navigation',
      'splash_assets',
      'metrics',
    ]) {
      expect(messages.some((message) => message.includes(`"${key}"`))).toBe(
        true,
      );
    }
  });

  it('refuses unsafe asset URLs and navigation hrefs', () => {
    // Test: Unsafe URLs in assets and navigation.
    // Situation: Each asset field and a navigation href contain a disallowed URL.
    // Expectation: Every asset falls back to its built-in default, `navigation`
    //              falls back to its default, and a warning is logged for each.
    const warn = spyOnWarn();
    writeSlot(
      JSON.stringify({
        logo: 'javascript:alert(1)',
        splash_assets: {
          thinking_indicator: 'data:image/svg+xml,<svg/>',
          done_indicator: '//evil.example/x.svg',
        },
        navigation: [{ label: 'Evil', href: 'javascript:alert(1)' }],
      }),
    );
    const config = getInstanceConfig();
    expect(config.logoUrl).toBe(DEFAULT_INSTANCE_CONFIG.logoUrl);
    expect(config.thinkingIndicatorUrl).toBe(
      DEFAULT_INSTANCE_CONFIG.thinkingIndicatorUrl,
    );
    expect(config.doneIndicatorUrl).toBe(
      DEFAULT_INSTANCE_CONFIG.doneIndicatorUrl,
    );
    expect(config.navigation).toEqual(DEFAULT_INSTANCE_CONFIG.navigation);
    expect(warn).toHaveBeenCalledTimes(4);
  });

  it('accepts hash-route, same-origin and http(s) navigation hrefs', () => {
    // Test: Allowed navigation href formats.
    // Situation: The navigation array contains a hash route, a root-relative path,
    //            and an https URL.
    // Expectation: All three navigation entries are preserved.
    const navigation = [
      { label: 'Dashboards', href: '#/metrics' },
      { label: 'Download', href: '/download' },
      { label: 'Docs', href: 'https://docs.datacommons.org/' },
    ];
    writeSlot(JSON.stringify({ navigation }));
    expect(getInstanceConfig().navigation).toEqual(navigation);
  });

  it('falls back to the defaults and warns on malformed JSON', () => {
    // Test: Malformed JSON in the instance-config element.
    // Situation: The element contains invalid JSON syntax.
    // Expectation: The built-in defaults are returned and a warning is logged.
    const warn = spyOnWarn();
    writeSlot('{"instanceName": ');
    expect(getInstanceConfig()).toEqual(DEFAULT_INSTANCE_CONFIG);
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('falls back to the defaults and warns when the JSON is not an object', () => {
    // Test: Non-object JSON in the instance-config element.
    // Situation: The element contains a valid JSON array instead of an object.
    // Expectation: The built-in defaults are returned and a warning is logged.
    const warn = spyOnWarn();
    writeSlot('["not", "an", "object"]');
    expect(getInstanceConfig()).toEqual(DEFAULT_INSTANCE_CONFIG);
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('caches the first resolution until reset', () => {
    // Test: Module-level configuration cache.
    // Situation: The DOM element is modified after the first call to
    //            `getInstanceConfig`, and then the cache is reset.
    // Expectation: Subsequent calls return the cached configuration until
    //              `resetInstanceConfigForTests` is called.
    writeSlot(JSON.stringify({ headline: 'First' }));
    const first = getInstanceConfig();
    writeSlot(JSON.stringify({ headline: 'Second' }));
    expect(getInstanceConfig()).toBe(first);
    expect(getInstanceConfig().headline).toBe('First');
    resetInstanceConfigForTests();
    expect(getInstanceConfig().headline).toBe('Second');
  });
});

describe('sanitizeUrl', () => {
  it.each([
    '/dc-logo.svg',
    'https://cdn.example/a.svg',
    'http://cdn.example/a.svg',
    'HTTPS://CDN.EXAMPLE/A.SVG',
  ])('passes %s through unchanged', (value) => {
    // Test: Allowed URL formats.
    // Situation: The value is a root-relative path or an absolute http(s) URL.
    // Expectation: The value is returned unchanged.
    expect(sanitizeUrl(value, '/fallback.svg')).toBe(value);
  });

  it.each([
    'javascript:alert(1)',
    'JAVASCRIPT:alert(1)',
    'java\nscript:alert(1)',
    'data:text/html,<script>',
    'vbscript:msgbox',
    'http:foo/bar.svg',
    'https:foo/bar.svg',
    '//evil.example/x.svg',
    '/\\evil.example/x.svg',
    'assets/logo.png',
  ])('returns the fallback for %j', (value) => {
    // Test: Disallowed URL formats.
    // Situation: The value uses a non-http(s) scheme, a protocol-relative URL,
    //            or a relative path without a leading slash.
    // Expectation: The fallback URL is returned and a warning is logged.
    const warn = spyOnWarn();
    expect(sanitizeUrl(value, '/fallback.svg')).toBe('/fallback.svg');
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it.each([
    '',
    42,
    null,
    undefined,
  ])('returns the fallback quietly for %j', (value) => {
    // Test: Empty or non-string values.
    // Situation: The value is an empty string or not a string.
    // Expectation: The fallback URL is returned without logging a warning.
    const warn = spyOnWarn();
    expect(sanitizeUrl(value, '/fallback.svg')).toBe('/fallback.svg');
    expect(warn).not.toHaveBeenCalled();
  });
});
