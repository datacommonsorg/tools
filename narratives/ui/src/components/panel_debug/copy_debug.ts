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
 * @fileoverview User-facing text of the debug panel: its chrome, section
 * headings, detail labels, and fallbacks.
 */

/** Text of the panel chrome: the open button, the dialog, and its close button. */
export const DEBUG_PANEL_COPY = {
  openButtonLabel: 'Inspect data sources for this answer',
  openButtonTitle: 'Inspect data sources',
  title: 'Provenance inspector',
  closeButtonLabel: 'Close provenance inspector',
  closeButtonGlyph: '×',
} as const;

/** Headings of the panel's body sections. */
export const DEBUG_SECTION_HEADINGS = {
  provenances: 'Provenances used',
  variables: 'Variables',
  charts: 'Charts requested',
} as const;

/** Labels of the key/value pairs on a facet's detail lines. */
export const DEBUG_FACET_DETAIL_LABELS = {
  coverage: 'coverage',
  observations: 'observations',
  unit: 'unit',
  license: 'license',
  facet: 'facet',
} as const;

/** Name shown for a facet whose dataset name is unknown. */
export const UNNAMED_SOURCE_LABEL = '(unnamed source)';

/** Separator between a variable's DCID and its display name. */
export const VARIABLE_NAME_SEPARATOR = ' — ';

/** Note on a variable found while searching but never fetched. */
export const RESOLVED_DURING_SEARCH_NOTE = ' (resolved during search)';

/** Marker appended to a tool call that finished with an error. */
export const TOOL_CALL_ERROR_MARKER = ' · error';

/** Returns the places section heading for `count` places. */
export const formatPlacesHeading = (count: number): string =>
  `Places (${count})`;

/** Returns the tool calls section heading for `count` calls. */
export const formatToolCallsHeading = (count: number): string =>
  `Tool calls (${count})`;

/** Returns the suffix that counts the places a requested chart covers. */
export const formatChartPlacesSuffix = (count: number): string =>
  ` @ ${count} place(s)`;

/**
 * Returns the label of a tool call's raw response toggle, naming the action
 * it performs and the response length in characters.
 */
export const formatRawResponseToggleLabel = (
  isOpen: boolean,
  characterCount: number,
): string =>
  `${isOpen ? 'Hide' : 'Show'} raw response (${characterCount.toLocaleString()} chars)`;
