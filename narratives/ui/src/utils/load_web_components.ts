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
 * @fileoverview Loads the Data Commons chart web components
 * (`datacommons.js`) from the URL the agent configures, so the script host
 * can change without rebuilding the UI.
 */

/** The id of the `<script>` element that loads `datacommons.js`. */
export const WEB_COMPONENTS_SCRIPT_ID = 'datacommons-web-components';

/**
 * Appends one `<script src={url}>` to `document.head` when `url` is non-empty.
 * Subsequent calls once the script element exists are no-ops, so the
 * components load at most once. Dynamically inserted scripts execute
 * asynchronously once loaded, so chart code waits for each custom element
 * with `customElements.whenDefined`.
 */
export const loadWebComponents = (url: string): void => {
  if (!url || document.getElementById(WEB_COMPONENTS_SCRIPT_ID)) {
    return;
  }
  const script = document.createElement('script');
  script.id = WEB_COMPONENTS_SCRIPT_ID;
  script.src = url;
  document.head.appendChild(script);
};
