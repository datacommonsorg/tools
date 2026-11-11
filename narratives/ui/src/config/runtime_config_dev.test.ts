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
 * @fileoverview Tests for resolveAgentShellUrl, extractRuntimeConfigText,
 * copyAgentRuntimeConfig, and stampRuntimeConfigHtml.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_RUNTIME_CONFIG,
  DEFAULT_UNAVAILABLE_MESSAGE,
} from '@/src/config/runtime_config';
import {
  copyAgentRuntimeConfig,
  extractRuntimeConfigText,
  resolveAgentShellUrl,
  stampRuntimeConfigHtml,
} from '@/src/config/runtime_config_dev';

const EMPTY_SLOT =
  '<script id="runtime-config" type="application/json"></script>';

const spyOnWarn = () => vi.spyOn(console, 'warn').mockReturnValue(undefined);

afterEach(() => {
  vi.restoreAllMocks();
});

describe('resolveAgentShellUrl', () => {
  it.each([
    ['http://localhost:5001', 'http://localhost:5001/'],
    ['http://localhost:5001/', 'http://localhost:5001/'],
    [
      'https://autopush.datacommons.org/narratives',
      'https://autopush.datacommons.org/narratives/',
    ],
    [
      'https://autopush.datacommons.org/narratives//',
      'https://autopush.datacommons.org/narratives/',
    ],
    ['https://host.example/a/b?x=1#top', 'https://host.example/a/b/'],
  ])('resolves AGENT_URL %s to %s', (agentUrl, expected) => {
    // Test: Shell URL derived from AGENT_URL.
    // Situation: AGENT_URL is a root URL, a root URL with a trailing slash, a
    //   subpath, a subpath with extra trailing slashes, or a subpath with a
    //   query and fragment.
    // Expectation: The origin and path are kept with one trailing slash, and
    //   the query and fragment are dropped.
    expect(resolveAgentShellUrl(agentUrl)).toBe(expected);
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

  it('requests the shell without following redirects', async () => {
    // Test: Fetch options for the agent shell.
    // Situation: The agent answers with a stamped shell.
    // Expectation: The request sets `redirect: 'manual'`.
    stubShellResponse(buildAgentShell('{"enable_chat":true}'));
    await copyAgentRuntimeConfig(EMPTY_SLOT, SHELL_URL);
    expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({
      redirect: 'manual',
    });
  });

  it.each([
    [
      'the request fails',
      () =>
        vi.stubGlobal(
          'fetch',
          vi.fn().mockRejectedValue(new TypeError('fetch failed')),
        ),
      'Start the agent at AGENT_URL.',
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
      'Start the agent at AGENT_URL.',
    ],
    [
      'the agent answers 404',
      () => stubShellResponse('Not Found', 404),
      '`pnpm build`',
    ],
    [
      'the agent answers 500',
      () => stubShellResponse('Internal Server Error', 500),
      'Start the agent at AGENT_URL.',
    ],
    [
      'the shell has an empty slot',
      () => stubShellResponse(`<head>${EMPTY_SLOT}</head>`),
      '`pnpm build`',
    ],
  ])('leaves the slot empty and warns once when %s', async (_, stubAgent, hint) => {
    // Test: Agent shell that cannot be read.
    // Situation: The fetch rejects, times out, answers a non-2xx status, or
    //   returns a shell without stamped text.
    // Expectation: The Vite page is returned unchanged and one warning names
    //   the shell URL and the matching hint.
    const warn = spyOnWarn();
    stubAgent();
    expect(await copyAgentRuntimeConfig(EMPTY_SLOT, SHELL_URL)).toBe(
      EMPTY_SLOT,
    );
    expect(warn).toHaveBeenCalledTimes(1);
    const message = String(warn.mock.calls[0][0]);
    expect(message).toContain(SHELL_URL);
    expect(message).toContain(hint);
  });

  it.each([
    [
      'a sign-in redirect',
      { location: 'https://accounts.google.com/o/oauth2/auth?x=1' },
      'HTTP 302 with a redirect to https://accounts.google.com',
    ],
    [
      'a redirect without a Location header',
      {},
      'HTTP 302 without a Location header',
    ],
  ])('reports %s instead of the build hint', async (_, headers, reason) => {
    // Test: Agent behind a sign-in such as IAP.
    // Situation: The agent answers `302 Found`, with or without a Location
    //   header.
    // Expectation: The Vite page is returned unchanged, and one warning names
    //   the status, the redirect origin when present, and the redirect hint,
    //   without the build hint.
    const warn = spyOnWarn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 302, headers })),
    );
    expect(await copyAgentRuntimeConfig(EMPTY_SLOT, SHELL_URL)).toBe(
      EMPTY_SLOT,
    );
    expect(warn).toHaveBeenCalledTimes(1);
    const message = String(warn.mock.calls[0][0]);
    expect(message).toContain(reason);
    expect(message).toContain('does not follow redirects');
    expect(message).not.toContain('pnpm build');
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
