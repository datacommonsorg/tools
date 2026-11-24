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
 * @fileoverview Tests for getRuntimeConfig: chat availability and the chart
 * host settings.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_RUNTIME_CONFIG,
  DEFAULT_UNAVAILABLE_MESSAGE,
  DEFAULT_UNAVAILABLE_TITLE,
  getRuntimeConfig,
  resetRuntimeConfigForTests,
} from '@/src/config/runtime_config';

/** The empty chart hosts and reCAPTCHA keys used when unconfigured. */
const EMPTY_OPTIONAL_SETTINGS = {
  webComponentUrl: '',
  webComponentApiRoot: '',
  recaptchaSessionSiteKey: '',
  recaptchaCheckboxSiteKey: '',
};

const writeRuntimeConfigSlot = (text: string): void => {
  document.getElementById('runtime-config')?.remove();
  const slot = document.createElement('script');
  slot.id = 'runtime-config';
  slot.type = 'application/json';
  slot.textContent = text;
  document.head.appendChild(slot);
};

const spyOnWarn = () => vi.spyOn(console, 'warn').mockReturnValue(undefined);

afterEach(() => {
  document.getElementById('runtime-config')?.remove();
  resetRuntimeConfigForTests();
  vi.restoreAllMocks();
});

describe('getRuntimeConfig', () => {
  it('returns the enabled defaults when the slot is absent', () => {
    // Test: Missing runtime-config element.
    // Situation: The document has no element with the id "runtime-config".
    // Expectation: Chat is enabled with the default message, without a
    //   warning.
    const warn = spyOnWarn();
    expect(getRuntimeConfig()).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(getRuntimeConfig().isChatEnabled).toBe(true);
    expect(warn).not.toHaveBeenCalled();
  });

  it.each([
    '',
    '   \n  ',
  ])('returns the enabled defaults quietly for slot text %j', (text) => {
    // Test: Empty runtime-config element, as served by the Vite build.
    // Situation: The element exists but holds no text or only whitespace.
    // Expectation: Chat is enabled with the default message, without a
    //   warning.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(text);
    expect(getRuntimeConfig()).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(warn).not.toHaveBeenCalled();
  });

  it('reads the stamped availability, title, and message', () => {
    // Test: Payload stamped by the agent server with chat disabled.
    // Situation: The element holds `enable_chat: false`, a custom title, and
    //   a custom message with surrounding whitespace.
    // Expectation: Chat is disabled, the title and message are trimmed, and
    //   nothing is logged.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: false,
        unavailable_title: ' Scheduled maintenance ',
        unavailable_message: ' Custom ',
      }),
    );
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableTitle: 'Scheduled maintenance',
      unavailableMessage: 'Custom',
      ...EMPTY_OPTIONAL_SETTINGS,
    });
    expect(warn).not.toHaveBeenCalled();
  });

  it('applies the defaults to omitted fields', () => {
    // Test: Payload that is an empty JSON object.
    // Situation: The element holds `{}`.
    // Expectation: Chat is enabled with the default title and message and
    //   empty chart hosts, without a warning.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot('{}');
    expect(getRuntimeConfig()).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(warn).not.toHaveBeenCalled();
  });

  it('fails closed and warns on malformed JSON', () => {
    // Test: Malformed JSON in the runtime-config element.
    // Situation: The element holds invalid JSON syntax.
    // Expectation: Chat is disabled with the default title and message, chart
    //   hosts remain empty, and one warning is logged.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot('{"enable_chat": ');
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableTitle: DEFAULT_UNAVAILABLE_TITLE,
      unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
      ...EMPTY_OPTIONAL_SETTINGS,
    });
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it.each([
    '[]',
    '"off"',
    'false',
    'null',
  ])('fails closed and warns when the JSON %s is not an object', (text) => {
    // Test: Valid JSON that is not an object.
    // Situation: The element holds an array, a string, a boolean, or null.
    // Expectation: Chat is disabled with the default title and message, chart
    //   hosts remain empty, and one warning is logged.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(text);
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableTitle: DEFAULT_UNAVAILABLE_TITLE,
      unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
      ...EMPTY_OPTIONAL_SETTINGS,
    });
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it.each([
    'false',
    'true',
    0,
    1,
    null,
  ])('fails closed and names the key when enable_chat is %j', (value) => {
    // Test: An `enable_chat` that is not a JSON boolean.
    // Situation: The element holds `enable_chat` as a string, a number, or
    //   null.
    // Expectation: Chat is disabled and one warning names "enable_chat".
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(JSON.stringify({ enable_chat: value }));
    expect(getRuntimeConfig().isChatEnabled).toBe(false);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('"enable_chat"');
  });

  it.each([
    '',
    '   ',
    42,
    null,
  ])('falls back to the default title and names the key when unavailable_title is %j', (value) => {
    // Test: An `unavailable_title` that is blank or not a string.
    // Situation: The element holds chat disabled and an unusable title.
    // Expectation: The default title applies, chat stays disabled, and one
    //   warning names "unavailable_title".
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({ enable_chat: false, unavailable_title: value }),
    );
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableTitle: DEFAULT_UNAVAILABLE_TITLE,
      unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
      ...EMPTY_OPTIONAL_SETTINGS,
    });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('"unavailable_title"');
  });

  it.each([
    '',
    '   ',
    42,
    null,
  ])('falls back to the default message and names the key when unavailable_message is %j', (value) => {
    // Test: An `unavailable_message` that is blank or not a string.
    // Situation: The element holds chat disabled and an unusable message.
    // Expectation: The default message applies, chat stays disabled, and one
    //   warning names "unavailable_message".
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({ enable_chat: false, unavailable_message: value }),
    );
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableTitle: DEFAULT_UNAVAILABLE_TITLE,
      unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
      ...EMPTY_OPTIONAL_SETTINGS,
    });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('"unavailable_message"');
  });

  it('parses and trims optional reCAPTCHA site keys and ignores non-strings without disabling chat', () => {
    // Test: Parsing `recaptcha_session_site_key` and `recaptcha_checkbox_site_key`.
    // Situation: `#runtime-config` supplies whitespace-padded site keys,
    //            whitespace-only site keys, `null` site keys, and finally
    //            non-string values.
    // Expectation: String keys are trimmed; whitespace-only strings and `null`
    //              resolve silently to `""`; other non-strings warn naming each
    //              key and fall back to `""` while keeping `isChatEnabled: true`.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: true,
        recaptcha_session_site_key: '  6Lc_session_key \n',
        recaptcha_checkbox_site_key: '\t6Lc_checkbox_key  ',
      }),
    );
    expect(getRuntimeConfig()).toEqual({
      ...DEFAULT_RUNTIME_CONFIG,
      recaptchaSessionSiteKey: '6Lc_session_key',
      recaptchaCheckboxSiteKey: '6Lc_checkbox_key',
    });
    expect(warn).not.toHaveBeenCalled();

    resetRuntimeConfigForTests();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: true,
        recaptcha_session_site_key: '   ',
        recaptcha_checkbox_site_key: '\t\n',
      }),
    );
    expect(getRuntimeConfig()).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(warn).not.toHaveBeenCalled();

    resetRuntimeConfigForTests();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: true,
        recaptcha_session_site_key: null,
        recaptcha_checkbox_site_key: null,
      }),
    );
    expect(getRuntimeConfig()).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(warn).not.toHaveBeenCalled();

    resetRuntimeConfigForTests();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: true,
        recaptcha_session_site_key: 123,
        recaptcha_checkbox_site_key: { invalid: true },
      }),
    );
    expect(getRuntimeConfig()).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(warn).toHaveBeenCalledTimes(2);
    expect(String(warn.mock.calls[0][0])).toContain(
      '"recaptcha_session_site_key"',
    );
    expect(String(warn.mock.calls[1][0])).toContain(
      '"recaptcha_checkbox_site_key"',
    );
  });

  it('caches the first resolution until reset', () => {
    // Test: Module-level configuration cache.
    // Situation: The element changes after the first call, and the cache is
    //   then reset.
    // Expectation: Calls return the cached object until
    //   `resetRuntimeConfigForTests` runs, after which the new text is read.
    writeRuntimeConfigSlot(JSON.stringify({ enable_chat: false }));
    const first = getRuntimeConfig();
    writeRuntimeConfigSlot(JSON.stringify({ enable_chat: true }));
    expect(getRuntimeConfig()).toBe(first);
    expect(getRuntimeConfig().isChatEnabled).toBe(false);
    resetRuntimeConfigForTests();
    expect(getRuntimeConfig().isChatEnabled).toBe(true);
  });
});

describe('getRuntimeConfig chart hosts', () => {
  it('reads the configured chart hosts', () => {
    // Test: Chart hosts stamped by an agent that overrides both settings.
    // Situation: The element names autopush for `web_component_url` and
    //   `http://localhost:8080/` for `web_component_api_root`.
    // Expectation: The URL is read unchanged, the API root is read as an
    //   origin without its trailing slash, chat stays enabled, and nothing
    //   is logged.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: true,
        web_component_url: 'https://autopush.datacommons.org/datacommons.js',
        web_component_api_root: 'http://localhost:8080/',
      }),
    );
    expect(getRuntimeConfig()).toEqual({
      ...DEFAULT_RUNTIME_CONFIG,
      webComponentUrl: 'https://autopush.datacommons.org/datacommons.js',
      webComponentApiRoot: 'http://localhost:8080',
    });
    expect(warn).not.toHaveBeenCalled();
  });

  it.each([
    '',
    'datacommons.org/datacommons.js',
    '//datacommons.org/datacommons.js',
    'javascript:alert(1)',
    'ftp://datacommons.org/datacommons.js',
    'https://user@datacommons.org/datacommons.js',
    'https://:secret@datacommons.org/datacommons.js',
    'https:\\\\datacommons.org/datacommons.js',
    'https://datacommons.org/datacommons.js ',
    'https://datacommons.org/\u0007.js',
    'https://datacommons.org/\u007f.js',
    'https://datacommons.org:99999/datacommons.js',
    42,
    null,
  ])('keeps chat enabled and disables chart script loading for web_component_url %j', (value) => {
    // Test: Invalid `web_component_url`.
    // Situation: The value is empty, not an absolute http(s) URL, carries
    //   credentials, backslashes, whitespace, ASCII control characters, or an
    //   out-of-range port, or is not a string.
    // Expectation: `webComponentUrl` resolves to `""` rather than falling
    //   back to a default host, chat stays enabled, and one warning names
    //   "web_component_url".
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: true,
        web_component_url: value,
        web_component_api_root: 'https://autopush.datacommons.org',
      }),
    );
    expect(getRuntimeConfig()).toEqual({
      ...DEFAULT_RUNTIME_CONFIG,
      webComponentUrl: '',
      webComponentApiRoot: 'https://autopush.datacommons.org',
    });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('"web_component_url"');
  });

  it.each([
    '',
    'datacommons.org',
    'javascript:alert(1)',
    'https://user@datacommons.org',
    'https:\\\\datacommons.org',
    'https://datacommons.org/api',
    'https://datacommons.org//',
    'https://datacommons.org?x=1',
    'https://datacommons.org/?',
    'https://datacommons.org#top',
    'https://datacommons.org ',
    'https://datacommons.org\u0007',
    'https://datacommons.org:99999',
    42,
    null,
  ])('keeps chat enabled and omits apiroot for web_component_api_root %j', (value) => {
    // Test: Invalid `web_component_api_root`.
    // Situation: The value is empty, not an http(s) origin, carries
    //   credentials, a path, query, fragment, backslash, whitespace, ASCII
    //   control character, or out-of-range port, or is not a string.
    // Expectation: `webComponentApiRoot` resolves to `""` rather than falling
    //   back to a default host, chat stays enabled, and one warning names
    //   "web_component_api_root".
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({
        enable_chat: true,
        web_component_url: 'https://autopush.datacommons.org/datacommons.js',
        web_component_api_root: value,
      }),
    );
    expect(getRuntimeConfig()).toEqual({
      ...DEFAULT_RUNTIME_CONFIG,
      webComponentUrl: 'https://autopush.datacommons.org/datacommons.js',
      webComponentApiRoot: '',
    });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('"web_component_api_root"');
  });
});
