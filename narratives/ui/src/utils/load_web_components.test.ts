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
 * @fileoverview Tests for loadWebComponents.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  loadWebComponents,
  WEB_COMPONENTS_SCRIPT_ID,
} from '@/src/utils/load_web_components';

const AUTOPUSH_URL = 'https://autopush.datacommons.org/datacommons.js';

/** Returns every `<script>` element in the document head. */
const getHeadScripts = (): HTMLScriptElement[] => [
  ...document.head.querySelectorAll('script'),
];

/** The part of the happy-dom window API that controls file loading. */
interface HappyDomWindow {
  happyDOM: { settings: { handleDisabledFileLoadingAsSuccess: boolean } };
}

const happyDomSettings = (window as unknown as HappyDomWindow).happyDOM
  .settings;

// happy-dom does not load script files, and it logs an error for each skipped
// script unless `handleDisabledFileLoadingAsSuccess` makes it report the
// script as loaded.
beforeEach(() => {
  happyDomSettings.handleDisabledFileLoadingAsSuccess = true;
});

afterEach(() => {
  document.getElementById(WEB_COMPONENTS_SCRIPT_ID)?.remove();
  happyDomSettings.handleDisabledFileLoadingAsSuccess = false;
});

describe('loadWebComponents', () => {
  it('appends nothing when the URL is empty', () => {
    // Test: Unconfigured or invalid chart script URL.
    // Situation: `loadWebComponents` receives an empty string, then a valid
    //   URL on a subsequent call.
    // Expectation: The empty call appends no script, and a later call with a
    //   configured URL still loads the bundle.
    loadWebComponents('');
    expect(getHeadScripts()).toHaveLength(0);

    loadWebComponents(AUTOPUSH_URL);
    const scripts = getHeadScripts();
    expect(scripts).toHaveLength(1);
    expect(scripts[0].getAttribute('src')).toBe(AUTOPUSH_URL);
  });

  it('appends one script for the configured URL', () => {
    // Test: First load of the chart web components.
    // Situation: The head holds no web components script, and the
    //   configured URL names autopush.
    // Expectation: The head gains one script whose source is the configured
    //   URL.
    loadWebComponents(AUTOPUSH_URL);

    const scripts = getHeadScripts();
    expect(scripts).toHaveLength(1);
    expect(scripts[0].getAttribute('src')).toBe(AUTOPUSH_URL);
  });

  it('adds no second script when called again', () => {
    // Test: Repeated loads.
    // Situation: The loader runs twice, the second time with another URL.
    // Expectation: The head holds one script, still for the first URL.
    loadWebComponents(AUTOPUSH_URL);
    loadWebComponents('https://datacommons.org/datacommons.js');

    const scripts = getHeadScripts();
    expect(scripts).toHaveLength(1);
    expect(scripts[0].getAttribute('src')).toBe(AUTOPUSH_URL);
  });
});
