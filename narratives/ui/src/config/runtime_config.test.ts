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
 * @fileoverview Tests for getRuntimeConfig.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_RUNTIME_CONFIG,
  DEFAULT_UNAVAILABLE_MESSAGE,
  getRuntimeConfig,
  resetRuntimeConfigForTests,
} from '@/src/config/runtime_config';

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
