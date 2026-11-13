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
 * Appends one `<script src={url} defer>` to `document.head`. A later call
 * adds nothing, so the components are loaded once. An inserted script runs
 * asynchronously once loaded, possibly after the first render, so chart code
 * waits for each element with `customElements.whenDefined`.
 */
export const loadWebComponents = (url: string): void => {
  if (document.getElementById(WEB_COMPONENTS_SCRIPT_ID)) {
    return;
  }
  const script = document.createElement('script');
  script.id = WEB_COMPONENTS_SCRIPT_ID;
  script.src = url;
  script.defer = true;
  document.head.appendChild(script);
};
