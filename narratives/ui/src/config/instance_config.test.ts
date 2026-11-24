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

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_INSTANCE_CONFIG,
  getInstanceConfig,
  METRICS_TILE_ATTRIBUTE_NAMES,
  resetInstanceConfigForTests,
  sanitizeUrl,
} from '@/src/config/instance_config';

const writeSlot = (text: string): void => {
  document.head.innerHTML = '';
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = text;
  document.head.appendChild(slot);
};

/**
 * The path of `schemas/theme.schema.json`, resolved from this file's directory
 * so that the tests do not depend on the working directory.
 */
const THEME_SCHEMA_PATH = resolve(
  import.meta.dirname,
  '../../../schemas/theme.schema.json',
);

/** The parts of `schemas/theme.schema.json` these tests read. */
interface ThemeSchema {
  $defs: {
    assetUrl: { pattern: string };
    linkHref: { pattern: string };
    metricsTile: {
      properties: Record<string, unknown>;
      required: string[];
    };
  };
}

const readThemeSchema = (): ThemeSchema =>
  JSON.parse(readFileSync(THEME_SCHEMA_PATH, 'utf8'));

const spyOnWarn = () => vi.spyOn(console, 'warn').mockReturnValue(undefined);

afterEach(() => {
  document.head.innerHTML = '';
  resetInstanceConfigForTests();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
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

  it('resolves default asset URLs relative to the document subpath', () => {
    // Test: Built-in default asset URLs when mounted under a runtime subpath.
    // Situation: `window.location` is at `/labs/discover/` and no
    //   `#instance-config` overrides are present.
    // Expectation: `logoUrl`, `thinkingIndicatorUrl`, and `doneIndicatorUrl`
    //   resolve under `/labs/discover/`.
    vi.stubGlobal(
      'location',
      new URL('https://autopush.datacommons.org/labs/discover/'),
    );
    document.head.innerHTML = '';
    const config = getInstanceConfig();
    expect(config.logoUrl).toBe('/labs/discover/dc-logo.svg');
    expect(config.thinkingIndicatorUrl).toBe(
      '/labs/discover/agent-thinking.svg',
    );
    expect(config.doneIndicatorUrl).toBe(
      '/labs/discover/agent-done-thinking.svg',
    );
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
        logo_href: 'https://acme.example/',
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
      logoHref: 'https://acme.example/',
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
    [
      'omits logo_text and logo_alt on a custom instance',
      { instance_name: 'Acme', logo: '/theme/acme.svg' },
    ],
    [
      'sets logo_text and logo_alt to empty strings',
      { logo_text: '', logo_alt: '' },
    ],
  ])('leaves logoText and logoAlt empty when the document %s', (_, themeDocument) => {
    // Test: Wordmark and logo alt text when `logo_text` and `logo_alt` are omitted
    //       on a custom instance or explicitly set to empty strings.
    // Situation: The element contains a theme document with a custom identity that
    //            omits `logo_text` and `logo_alt`, or a document that sets them to
    //            empty strings.
    // Expectation: `logoText` and `logoAlt` resolve to empty strings so a custom
    //              instance does not inherit the "Data Commons" wordmark or alt text.
    writeSlot(JSON.stringify(themeDocument));
    expect(getInstanceConfig().logoText).toBe('');
    expect(getInstanceConfig().logoAlt).toBe('');
  });

  it('preserves the default logoText and logoAlt when neither logo nor instance_name is overridden', () => {
    // Test: Partial override without custom identity fields.
    // Situation: The theme document overrides `headline` without setting `logo`,
    //            `instance_name`, `logo_text`, or `logo_alt`.
    // Expectation: `logoText` and `logoAlt` retain the Base Data Commons defaults.
    writeSlot(JSON.stringify({ headline: 'Custom headline' }));
    const config = getInstanceConfig();
    expect(config.headline).toBe('Custom headline');
    expect(config.logoText).toBe(DEFAULT_INSTANCE_CONFIG.logoText);
    expect(config.logoAlt).toBe(DEFAULT_INSTANCE_CONFIG.logoAlt);
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
    // Situation: Each asset field, the logo link, and a navigation href contain
    //            a disallowed URL.
    // Expectation: Every asset falls back to its built-in default, `logoHref`
    //              and `navigation` fall back to their defaults, and a warning
    //              is logged for each.
    const warn = spyOnWarn();
    writeSlot(
      JSON.stringify({
        logo: 'javascript:alert(1)',
        logo_href: 'javascript:alert(1)',
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
    expect(config.logoHref).toBe(DEFAULT_INSTANCE_CONFIG.logoHref);
    expect(config.navigation).toEqual(DEFAULT_INSTANCE_CONFIG.navigation);
    expect(warn).toHaveBeenCalledTimes(5);
  });

  it.each([
    ['javascript:', 'javascript:alert(1)'],
    ['data:', 'data:text/html,<script>alert(1)</script>'],
    ['vbscript:', 'vbscript:msgbox(1)'],
  ])('falls back to the defaults for a %s logo, logo link, and navigation href', (_, value) => {
    // Test: Script and data URLs in the logo, the logo link, and navigation.
    // Situation: `logo`, `logo_href`, and the only navigation href hold the
    //            same script or data URL.
    // Expectation: `logoUrl`, `logoHref`, and `navigation` fall back to their
    //              defaults.
    spyOnWarn();
    writeSlot(
      JSON.stringify({
        logo: value,
        logo_href: value,
        navigation: [{ label: 'Evil', href: value }],
      }),
    );
    const config = getInstanceConfig();
    expect(config.logoUrl).toBe(DEFAULT_INSTANCE_CONFIG.logoUrl);
    expect(config.logoHref).toBe(DEFAULT_INSTANCE_CONFIG.logoHref);
    expect(config.navigation).toEqual(DEFAULT_INSTANCE_CONFIG.navigation);
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

  it('reads a tagline link from the theme document', () => {
    // Test: Valid `tagline_link` overrides, with and without `sources`.
    // Situation: The theme document sets a tagline containing the phrase and
    //            `tagline_link` with one section and a sources link, then
    //            again without `sources`.
    // Expectation: `taglineLink` holds the configured phrase, sections, and
    //              sources; without `sources` it parses with `sources`
    //              undefined. No warning is logged.
    const warn = spyOnWarn();
    const taglineLink = {
      text: 'Acme Graph',
      sections: [{ title: 'Acme Graph', body: 'What the graph holds.' }],
      sources: { label: 'Sources', href: 'https://acme.example/sources' },
    };
    const tagline = 'Answers from the Acme Graph';
    writeSlot(JSON.stringify({ tagline, tagline_link: taglineLink }));
    expect(getInstanceConfig().taglineLink).toEqual(taglineLink);

    resetInstanceConfigForTests();
    const { sources: _, ...withoutSources } = taglineLink;
    writeSlot(JSON.stringify({ tagline, tagline_link: withoutSources }));
    expect(getInstanceConfig().taglineLink).toEqual(withoutSources);
    expect(warn).not.toHaveBeenCalled();
  });

  it.each([
    ['has no sections', { text: 'Graph', sections: [] }],
    [
      'has a section without a body',
      { text: 'Graph', sections: [{ title: 'Graph' }] },
    ],
    [
      'has a non-string phrase',
      { text: 42, sections: [{ title: 'Graph', body: 'Body.' }] },
    ],
    [
      'has an empty phrase',
      { text: '', sections: [{ title: 'Graph', body: 'Body.' }] },
    ],
    [
      'has an empty section title',
      { text: 'Graph', sections: [{ title: '', body: 'Body.' }] },
    ],
    [
      'has an unsafe sources href',
      {
        text: 'Graph',
        sections: [{ title: 'Graph', body: 'Body.' }],
        sources: { label: 'Sources', href: 'javascript:alert(1)' },
      },
    ],
  ])('keeps the default tagline link when the override %s', (_, taglineLink) => {
    // Test: Malformed or unsafe `tagline_link` overrides.
    // Situation: `tagline_link` has empty sections, a section missing its
    //            body, a non-string or empty phrase, an empty section title,
    //            or a script URL as its sources href.
    // Expectation: `taglineLink` falls back to the default and one warning
    //              names `tagline_link`.
    const warn = spyOnWarn();
    writeSlot(JSON.stringify({ tagline_link: taglineLink }));
    expect(getInstanceConfig().taglineLink).toEqual(
      DEFAULT_INSTANCE_CONFIG.taglineLink,
    );
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0]?.[0])).toContain('"tagline_link"');
  });

  it.each([
    ['warns when the theme link phrase is missing', true, 1],
    ['stays quiet for the default link', false, 0],
  ])('%s from a custom tagline', (_, setsLink, warnings) => {
    // Test: A tagline that does not contain the link phrase.
    // Situation: The theme sets a custom tagline, with or without its own
    //            `tagline_link` whose phrase the tagline lacks.
    // Expectation: Only the theme's own link logs a warning, which names
    //              `tagline_link.text`; the default link is expected to go
    //              unmatched by a custom tagline.
    const warn = spyOnWarn();
    const taglineLink = {
      text: 'Acme Graph',
      sections: [{ title: 'Acme Graph', body: 'What the graph holds.' }],
    };
    writeSlot(
      JSON.stringify({
        tagline: 'Custom tagline',
        ...(setsLink && { tagline_link: taglineLink }),
      }),
    );
    getInstanceConfig();
    expect(warn).toHaveBeenCalledTimes(warnings);
    if (warnings) {
      expect(String(warn.mock.calls[0]?.[0])).toContain('"tagline_link.text"');
    }
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

describe('metrics tiles', () => {
  /** Writes a theme whose only metrics tab holds `tiles`. */
  const writeTiles = (tiles: Record<string, unknown>[]): void => {
    writeSlot(
      JSON.stringify({
        metrics: { tabs: [{ id: 'econ', label: 'Economy', tiles }] },
      }),
    );
  };

  it('passes the allowlisted attributes through', () => {
    // Test: Allowlisted tile attributes.
    // Situation: A ranking tile sets `variable`, `parentPlace`,
    //            `childPlaceType`, `rankingCount`, and `showLowest`.
    // Expectation: The tile keeps every attribute and no warning is logged.
    const warn = spyOnWarn();
    const tile = {
      type: 'ranking',
      title: 'GDP',
      variable: 'Amount_EconomicActivity_GrossDomesticProduction_Nominal',
      parentPlace: 'Earth',
      childPlaceType: 'Country',
      rankingCount: 5,
      showLowest: true,
    };
    writeTiles([tile]);
    expect(getInstanceConfig().metrics.tabs[0].tiles).toEqual([tile]);
    expect(warn).not.toHaveBeenCalled();
  });

  it('drops an attribute outside the allowlist and warns', () => {
    // Test: A tile attribute the schema does not list.
    // Situation: A line tile sets `onclick` and `apiroot` beside `variable`.
    // Expectation: The tile keeps `variable`, drops `onclick` and `apiroot`,
    //              and a warning names each dropped key.
    const warn = spyOnWarn();
    writeTiles([
      {
        type: 'line',
        title: 'Population',
        variable: 'Count_Person',
        onclick: 'alert(1)',
        apiroot: 'https://evil.example',
      },
    ]);
    expect(getInstanceConfig().metrics.tabs[0].tiles).toEqual([
      { type: 'line', title: 'Population', variable: 'Count_Person' },
    ]);
    const messages = warn.mock.calls.map((call) => String(call[0]));
    expect(messages).toHaveLength(2);
    expect(messages[0]).toContain('"onclick"');
    expect(messages[1]).toContain('"apiroot"');
  });

  it('drops allowlisted attributes whose values have the wrong type and warns', () => {
    // Test: Value-type checks on allowlisted tile attributes.
    // Situation: A ranking tile sets valid `variable`, `min`, and `sort` values
    //            alongside a string boolean (`"showLowest": "false"`), a
    //            non-integer `rankingCount`, a string `max`, an unknown `sort`
    //            order on a second tile, and an array `places`.
    // Expectation: Only attributes whose values match their schema types are
    //              kept, and a warning names each dropped attribute.
    const warn = spyOnWarn();
    writeTiles([
      {
        type: 'ranking',
        title: 'GDP',
        variable: 'Amount_EconomicActivity_GrossDomesticProduction_Nominal',
        min: 0,
        sort: 'descending',
        showLowest: 'false',
        rankingCount: 2.5,
        max: '100',
        places: ['country/USA', 'country/FRA'],
      },
      {
        type: 'ranking',
        title: 'Population',
        variable: 'Count_Person',
        sort: 'random',
      },
    ]);
    expect(getInstanceConfig().metrics.tabs[0].tiles).toEqual([
      {
        type: 'ranking',
        title: 'GDP',
        variable: 'Amount_EconomicActivity_GrossDomesticProduction_Nominal',
        min: 0,
        sort: 'descending',
      },
      {
        type: 'ranking',
        title: 'Population',
        variable: 'Count_Person',
      },
    ]);
    const messages = warn.mock.calls.map((call) => String(call[0]));
    expect(messages).toHaveLength(5);
    for (const key of ['showLowest', 'rankingCount', 'max', 'places', 'sort']) {
      expect(messages.some((message) => message.includes(`"${key}"`))).toBe(
        true,
      );
    }
  });

  it('drops a tile of an unknown type and warns', () => {
    // Test: A tile whose `type` is not a chart type.
    // Situation: The tab holds a `donut` tile and a `bar` tile.
    // Expectation: Only the `bar` tile remains, and a warning names the type.
    const warn = spyOnWarn();
    writeTiles([
      { type: 'donut', title: 'Share' },
      { type: 'bar', title: 'Income' },
    ]);
    expect(getInstanceConfig().metrics.tabs[0].tiles).toEqual([
      { type: 'bar', title: 'Income' },
    ]);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('"donut"');
  });

  it('allowlists exactly the attributes the schema lists for a tile', () => {
    // Test: Drift between the tile allowlist and `theme.schema.json`.
    // Situation: The schema's `metricsTile.properties` is read from disk.
    // Expectation: The allowlist equals those properties minus the required
    //              `type` and `title`.
    const { metricsTile } = readThemeSchema().$defs;
    const schemaAttributes = Object.keys(metricsTile.properties).filter(
      (name) => !metricsTile.required.includes(name),
    );
    expect([...METRICS_TILE_ATTRIBUTE_NAMES].sort()).toEqual(
      schemaAttributes.sort(),
    );
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
    '/assets\\logo.svg',
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

describe('DEFAULT_INSTANCE_CONFIG drift', () => {
  it.each([
    'defaults/theme.json',
    'schemas/theme.base-dc.example.json',
  ])('landing copy matches %s', (path) => {
    // Test: Default landing copy stays in sync with the shipped theme JSON.
    // Situation: The headline, tagline, tagline link, and suggestions are
    //            duplicated in `instance_config.ts` and `path`.
    // Expectation: Each value is identical in both.
    const theme = JSON.parse(
      // Resolved from this file, not the cwd. happy-dom replaces the global
      // `URL`, so `new URL(path, import.meta.url)` would not give a file path.
      readFileSync(resolve(import.meta.dirname, '../../..', path), 'utf8'),
    );
    expect(DEFAULT_INSTANCE_CONFIG.headline).toEqual(theme.headline);
    expect(DEFAULT_INSTANCE_CONFIG.tagline).toEqual(theme.tagline);
    expect(DEFAULT_INSTANCE_CONFIG.taglineLink).toEqual(theme.tagline_link);
    expect(DEFAULT_INSTANCE_CONFIG.suggestions).toEqual(theme.suggestions);
  });
});

describe('theme schema URL patterns', () => {
  // Each row holds a value, whether the UI accepts the value as an asset URL,
  // and whether the UI accepts it as a link target. Both the schema patterns
  // and the UI checks must match every row. The schema patterns restrict theme
  // URLs to printable ASCII characters (`0x21` to `0x7E` excluding `\`) without
  // parsing the host, so spaces and unencoded non-ASCII characters fail schema
  // validation while some malformed ports pass the schema and are rejected by
  // `new URL` in the UI.
  const URL_CASES: [string, boolean, boolean][] = [
    ['/', true, true],
    ['/dc-logo.svg', true, true],
    ['/download?format=csv#top', true, true],
    ['https://cdn.example/a.svg', true, true],
    ['HTTP://CDN.EXAMPLE/A.SVG', true, true],
    ['#/metrics', false, true],
    ['#', false, true],
    ['#/metrics\\evil', false, false],
    ['#/metrics\u0000', false, false],
    ['javascript:alert(1)', false, false],
    ['JAVASCRIPT:alert(1)', false, false],
    ['data:image/svg+xml,<svg/>', false, false],
    ['vbscript:msgbox', false, false],
    ['mailto:info@example.org', false, false],
    ['//evil.example/x.svg', false, false],
    ['/\\evil.example/x.svg', false, false],
    ['/assets\\logo.svg', false, false],
    ['/dc-logo.svg\n', false, false],
    ['https://cdn.example/\u0000a.svg', false, false],
    ['https://cdn.example/\u007fa.svg', false, false],
    ['assets/logo.png', false, false],
    ['http:foo/bar.svg', false, false],
    ['https://', false, false],
  ];

  it.each(URL_CASES)('agrees with the UI on %j', (value, isAsset, isLink) => {
    // Test: Parity between the deploy-time schema and the page-load checks.
    // Situation: One value is matched against the schema's `assetUrl` and
    //   `linkHref` patterns, passed to `sanitizeUrl`, and set as `logo_href`.
    // Expectation: Each pattern and each UI check accepts the value exactly
    //   when the row says it does.
    spyOnWarn();
    const { $defs } = readThemeSchema();
    expect(new RegExp($defs.assetUrl.pattern, 'u').test(value)).toBe(isAsset);
    expect(new RegExp($defs.linkHref.pattern, 'u').test(value)).toBe(isLink);
    expect(sanitizeUrl(value, '/fallback.svg') === value).toBe(isAsset);
    writeSlot(JSON.stringify({ logo_href: value }));
    expect(getInstanceConfig().logoHref === value).toBe(isLink);
  });
});
