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
 * @fileoverview Regex and parser for `[N]` and `[N, M]` citation markers.
 *
 * Single-source figures carry `[N]` and figures derived from multiple tables
 * carry `[N, M]`, where each number is a 1-based index into the turn's
 * provenance list. Whitespace inside a marker is horizontal only, so a marker
 * never spans a line break. `chip_citation`, `markdown_table`, and
 * `rehype_stream_words` all build on this grammar.
 */

/**
 * Source of the citation marker pattern: one or two digits per number,
 * separated by commas with optional spaces or tabs, inside square brackets.
 * The first capture group holds the numbers. Exported so other patterns can
 * embed the marker grammar rather than restate it.
 */
export const CITATION_MARKER_PATTERN_SOURCE = String.raw`\[(\d{1,2}(?:[ \t]*,[ \t]*\d{1,2})*)\]`;

/**
 * Returns a fresh global pattern over citation markers, whose first capture
 * group holds the comma-separated numbers inside the brackets. Each call
 * returns a new instance because a global `RegExp` tracks mutable `lastIndex`
 * state.
 */
export function createCitationMarkerPattern(): RegExp {
  return new RegExp(CITATION_MARKER_PATTERN_SOURCE, 'g');
}

/**
 * Parses the 1-based source numbers from a marker's capture group, without
 * duplicates, in order of first occurrence, so `[1, 1]` yields `[1]`.
 */
export function parseCitationNumbers(group: string): number[] {
  return [...new Set(group.split(',').map((part) => Number(part.trim())))];
}
