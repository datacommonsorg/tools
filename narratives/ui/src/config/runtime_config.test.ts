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
 * @fileoverview Tests for getRuntimeConfig, extractRuntimeConfigText,
 * copyAgentRuntimeConfig, and stampRuntimeConfigHtml.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  copyAgentRuntimeConfig,
  DEFAULT_RUNTIME_CONFIG,
  DEFAULT_UNAVAILABLE_MESSAGE,
  extractRuntimeConfigText,
  getRuntimeConfig,
  resetRuntimeConfigForTests,
  stampRuntimeConfigHtml,
} from '@/src/config/runtime_config';

const EMPTY_SLOT =
  '<script id="runtime-config" type="application/json"></script>';

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

  it('reads the stamped availability and message', () => {
    // Test: Payload stamped by the agent server with chat disabled.
    // Situation: The element holds `enable_chat: false` and a custom message
    //   with surrounding whitespace.
    // Expectation: Chat is disabled, the message is trimmed, and nothing is
    //   logged.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(
      JSON.stringify({ enable_chat: false, unavailable_message: ' Custom ' }),
    );
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableMessage: 'Custom',
    });
    expect(warn).not.toHaveBeenCalled();
  });

  it('applies the defaults to omitted fields', () => {
    // Test: Payload that is an empty JSON object.
    // Situation: The element holds `{}`.
    // Expectation: Chat is enabled with the default message, without a
    //   warning.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot('{}');
    expect(getRuntimeConfig()).toEqual(DEFAULT_RUNTIME_CONFIG);
    expect(warn).not.toHaveBeenCalled();
  });

  it('fails closed and warns on malformed JSON', () => {
    // Test: Malformed JSON in the runtime-config element.
    // Situation: The element holds invalid JSON syntax.
    // Expectation: Chat is disabled with the default message and one warning
    //   is logged.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot('{"enable_chat": ');
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
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
    // Expectation: Chat is disabled with the default message and one warning
    //   is logged.
    const warn = spyOnWarn();
    writeRuntimeConfigSlot(text);
    expect(getRuntimeConfig()).toEqual({
      isChatEnabled: false,
      unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
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
      unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
    });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('"unavailable_message"');
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

describe('extractRuntimeConfigText', () => {
  it('returns the trimmed text of a stamped element', () => {
    // Test: Shell stamped by the agent.
    // Situation: The HTML holds `#runtime-config` with JSON and whitespace.
    // Expectation: The JSON text is returned without the whitespace.
    expect(
      extractRuntimeConfigText(
        '<head><script id="runtime-config" type="application/json"> {"enable_chat":false} </script></head>',
      ),
    ).toBe('{"enable_chat":false}');
  });

  it.each([
    ['an empty element', `<head>${EMPTY_SLOT}</head>`],
    ['no element', '<head></head>'],
    [
      'an unterminated element',
      '<script id="runtime-config" type="application/json">{"enable_chat":false}',
    ],
  ])('returns undefined for HTML with %s', (_, html) => {
    // Test: Shell without stamped text.
    // Situation: The element is empty, absent, or has no closing tag.
    // Expectation: `undefined` is returned.
    expect(extractRuntimeConfigText(html)).toBeUndefined();
  });
});

describe('copyAgentRuntimeConfig', () => {
  const SHELL_URL = 'http://127.0.0.1:5011/';

  /** Stubs `fetch` to answer with `body` and `status`. */
  const stubShellResponse = (body: string, status = 200): void => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(body, { status })),
    );
  };

  /** Returns an agent shell whose slot holds `payload`. */
  const buildAgentShell = (payload: string): string =>
    `<head><script id="runtime-config" type="application/json">${payload}</script></head>`;

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    false,
    true,
  ])('copies enable_chat %s and the message from the agent shell', async (isChatEnabled) => {
    // Test: Agent with chat disabled or enabled.
    // Situation: The agent shell is stamped with the given `enable_chat` and
    //   a custom message.
    // Expectation: The empty slot in the Vite page receives the same values,
    //   and the agent shell URL is the one requested.
    stubShellResponse(
      buildAgentShell(
        JSON.stringify({
          enable_chat: isChatEnabled,
          unavailable_message: 'Paused',
        }),
      ),
    );
    const stamped = await copyAgentRuntimeConfig(EMPTY_SLOT, SHELL_URL);
    expect(stamped).toBe(
      `<script id="runtime-config" type="application/json">{"enable_chat":${isChatEnabled},"unavailable_message":"Paused"}</script>`,
    );
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(SHELL_URL);
  });

  it('re-escapes the copied message', async () => {
    // Test: Message with markup and line separator characters.
    // Situation: The agent shell carries a message holding `<`, `>`, `&`,
    //   U+2028, and U+2029 inside the text (edge whitespace is trimmed),
    //   escaped as the agent stamps it.
    // Expectation: The Vite page carries the same `\u` escapes.
    stubShellResponse(
      buildAgentShell(
        '{"enable_chat":false,"unavailable_message":"\\u003cb\\u003e\\u2028\\u0026\\u2029x"}',
      ),
    );
    const stamped = await copyAgentRuntimeConfig(EMPTY_SLOT, SHELL_URL);
    expect(stamped).toContain(
      '"unavailable_message":"\\u003cb\\u003e\\u2028\\u0026\\u2029x"',
    );
  });

  it('fails closed on a malformed agent payload', async () => {
    // Test: Agent shell with malformed JSON in its slot.
    // Situation: The stamped text is not valid JSON.
    // Expectation: The Vite page is stamped with chat disabled and the
    //   default message, and a warning is logged.
    const warn = spyOnWarn();
    stubShellResponse(buildAgentShell('{"enable_chat": '));
    const stamped = await copyAgentRuntimeConfig(EMPTY_SLOT, SHELL_URL);
    expect(stamped).toBe(
      `<script id="runtime-config" type="application/json">{"enable_chat":false,"unavailable_message":"${DEFAULT_UNAVAILABLE_MESSAGE}"}</script>`,
    );
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it.each([
    [
      'the request fails',
      () =>
        vi.stubGlobal(
          'fetch',
          vi.fn().mockRejectedValue(new TypeError('fetch failed')),
        ),
    ],
    [
      'the request times out',
      () =>
        vi.stubGlobal(
          'fetch',
          vi
            .fn()
            .mockRejectedValue(
              new DOMException('The operation timed out.', 'TimeoutError'),
            ),
        ),
    ],
    ['the agent answers 404', () => stubShellResponse('Not Found', 404)],
    [
      'the shell has an empty slot',
      () => stubShellResponse(`<head>${EMPTY_SLOT}</head>`),
    ],
  ])('leaves the slot empty and warns once when %s', async (_, stubAgent) => {
    // Test: Agent shell that cannot be read.
    // Situation: The fetch rejects, times out, answers a non-2xx status, or
    //   returns a shell without stamped text.
    // Expectation: The Vite page is returned unchanged and one warning names
    //   the shell URL.
    const warn = spyOnWarn();
    stubAgent();
    expect(await copyAgentRuntimeConfig(EMPTY_SLOT, SHELL_URL)).toBe(
      EMPTY_SLOT,
    );
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain(SHELL_URL);
  });
});

describe('stampRuntimeConfigHtml', () => {
  it('stamps the wire JSON into the empty slot', () => {
    // Test: Stamping the HTML shell.
    // Situation: The HTML holds the empty slot and chat is disabled.
    // Expectation: The slot holds the compact wire JSON with snake_case keys.
    const html = `<head>${EMPTY_SLOT}</head>`;
    expect(
      stampRuntimeConfigHtml(html, {
        isChatEnabled: false,
        unavailableMessage: 'Paused',
      }),
    ).toBe(
      '<head><script id="runtime-config" type="application/json">{"enable_chat":false,"unavailable_message":"Paused"}</script></head>',
    );
  });

  it('escapes characters that could end the element or a JavaScript string', () => {
    // Test: Message with markup and line separator characters.
    // Situation: The message holds `<`, `>`, `&`, U+2028, and U+2029.
    // Expectation: Each is written as its `\u` escape, and the payload still
    //   parses back to the original message.
    const message = '</script><b>&\u2028\u2029';
    const stamped = stampRuntimeConfigHtml(EMPTY_SLOT, {
      isChatEnabled: false,
      unavailableMessage: message,
    });
    expect(stamped).toContain(
      '"unavailable_message":"\\u003c/script\\u003e\\u003cb\\u003e\\u0026\\u2028\\u2029"',
    );
    const payload = stamped
      .replace('<script id="runtime-config" type="application/json">', '')
      .replace(/<\/script>$/, '');
    expect(JSON.parse(payload).unavailable_message).toBe(message);
  });

  it('keeps dollar sequences in the message literal', () => {
    // Test: Message with `String.prototype.replace` substitution patterns.
    // Situation: The message holds `$$`, `` $` ``, and `$'`.
    // Expectation: The sequences appear verbatim in the stamped JSON.
    const stamped = stampRuntimeConfigHtml(EMPTY_SLOT, {
      isChatEnabled: false,
      unavailableMessage: "Costs $$ and $` and $'",
    });
    expect(stamped).toContain(
      '"unavailable_message":"Costs $$ and $` and $\'"',
    );
  });

  it('stamps only the first empty slot', () => {
    // Test: HTML with two empty slots.
    // Situation: The empty slot appears twice.
    // Expectation: Only the first occurrence is stamped.
    const stamped = stampRuntimeConfigHtml(
      `${EMPTY_SLOT}${EMPTY_SLOT}`,
      DEFAULT_RUNTIME_CONFIG,
    );
    expect(stamped.endsWith(EMPTY_SLOT)).toBe(true);
    expect(stamped.startsWith(EMPTY_SLOT)).toBe(false);
  });

  it.each([
    ['HTML without the slot', '<head></head>'],
    [
      'HTML with an already stamped slot',
      '<script id="runtime-config" type="application/json">{"enable_chat":false}</script>',
    ],
  ])('returns %s unchanged', (_, html) => {
    // Test: HTML without an empty runtime-config element.
    // Situation: The HTML lacks the slot, or its slot already holds JSON.
    // Expectation: The HTML is returned unchanged.
    expect(stampRuntimeConfigHtml(html, DEFAULT_RUNTIME_CONFIG)).toBe(html);
  });
});
