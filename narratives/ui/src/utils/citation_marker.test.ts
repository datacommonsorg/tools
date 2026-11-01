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

/** @fileoverview Tests citation marker matching and number parsing. */

import { describe, expect, it } from 'vitest';
import {
  createCitationMarkerPattern,
  parseCitationNumbers,
} from './citation_marker';

/** Parses the numbers of every citation marker in `text`, one array per marker. */
function parseMarkers(text: string): number[][] {
  return [...text.matchAll(createCitationMarkerPattern())].map((match) =>
    parseCitationNumbers(match[1]),
  );
}

describe('createCitationMarkerPattern', () => {
  it('accepts single and composite markers', () => {
    // Test: Single and composite citation markers.
    // Situation: A single marker, a composite marker with a space, a composite
    //   marker without a space, and two markers with one- and two-digit numbers.
    // Expectation: Each marker is matched and its numbers are parsed in order.
    expect(parseMarkers('[1]')).toEqual([[1]]);
    expect(parseMarkers('[1, 2]')).toEqual([[1, 2]]);
    expect(parseMarkers('[1,2]')).toEqual([[1, 2]]);
    expect(parseMarkers('[12, 3] and [99]')).toEqual([[12, 3], [99]]);
  });

  it('rejects brackets that are not a marker', () => {
    // Test: Boundaries of the marker syntax.
    // Situation: A three-digit number, a trailing comma, a letter, a
    //   space-padded number, and empty brackets.
    // Expectation: None matches as a citation marker.
    for (const text of ['[123]', '[1,]', '[1, b]', '[ 1 ]', '[]']) {
      expect(parseMarkers(text)).toEqual([]);
    }
  });

  it('returns a fresh pattern on every call', () => {
    // Test: Isolation of the global pattern's state.
    // Situation: One pattern is advanced by a match before another is
    //   requested.
    // Expectation: The second pattern starts from index 0 of its input, so one
    //   caller's `lastIndex` cannot skip another caller's marker.
    const first = createCitationMarkerPattern();
    first.exec('[1] [2]');

    const second = createCitationMarkerPattern();

    expect(second).not.toBe(first);
    expect(second.lastIndex).toBe(0);
    expect(second.exec('[1] [2]')?.index).toBe(0);
  });
});

describe('parseCitationNumbers', () => {
  it('drops repeated numbers in order of first occurrence', () => {
    // Test: A marker that repeats a source.
    // Situation: The capture groups of `[1, 1]` and `[2, 1, 2]`.
    // Expectation: Each number appears once, in the order it first appears.
    expect(parseCitationNumbers('1, 1')).toEqual([1]);
    expect(parseCitationNumbers('2, 1, 2')).toEqual([2, 1]);
  });
});
