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

import { describe, expect, it } from 'vitest';
import {
  isSectionHeading,
  readSectionHeadingLabel,
} from '@/src/components/heading_section';

describe('isSectionHeading', () => {
  it.each([
    ['a level-two heading', '## Population by sex'],
    ['a heading of another level', '#### Population by sex'],
    ['a bold label', '## **Population by sex**'],
    ['a label with a closing colon', '## Population by sex:'],
    ['a heading with closing hashes', '## Population by sex ##'],
    ['a heading with trailing spaces', '## Population by sex  '],
  ])('accepts %s', (_, markdown) => {
    // Test: Lines that render as a section heading.
    // Situation: One Markdown heading line with a plain label, at any
    //   level, optionally in bold, with a closing colon, or with closing
    //   hashes.
    // Expectation: It is a section heading.
    expect(isSectionHeading(markdown)).toBe(true);
  });

  it.each([
    ['a label ending with a colon', 'Population by sex:'],
    ['a bold label ending with a colon', '**Population by sex:**'],
    [
      'a sentence ending with a colon',
      'These related statistics are available instead:',
    ],
    ['a sentence', 'The population rose.'],
    ['a list item', '- **Female:**'],
    ['a table row', '| Country: |'],
    ['a hash with no space after it', '#Population'],
    ['two lines', '## Population by sex\n- **Female:** 51%'],
    ['a label with a citation marker', '## Population by sex [1]'],
    ['a label with inner bold', '## **Canada** by sex'],
    ['an empty label', '## **:**'],
    ['a label with a backslash escape', '## Births \\(per 1,000\\)'],
    ['a label with an HTML entity', '## R&amp;D spending'],
  ])('rejects %s', (_, markdown) => {
    // Test: Lines that do not render as a section heading.
    // Situation: A label or a sentence that only ends with a colon, a
    //   sentence, a list item, a table row, a hash with no space after it,
    //   a block of more than one line, or a heading whose label holds a
    //   citation marker, inline Markdown, a backslash escape, an HTML
    //   entity, or no letter or digit.
    // Expectation: It is not a section heading, so it renders as text.
    expect(isSectionHeading(markdown)).toBe(false);
  });
});

describe('readSectionHeadingLabel', () => {
  it.each([
    ['## Population by sex', 'Population by sex'],
    ['## **Population by sex**', 'Population by sex'],
    ['## Population by sex:', 'Population by sex'],
    ['### _Ratio: women to men_', 'Ratio: women to men'],
    ['Population by sex:', ''],
  ])('reads the label of %s', (markdown, label) => {
    // Test: The heading text of a heading line.
    // Situation: A heading line, plain, wrapped in emphasis, or closed by
    //   a colon, and a line that is not a heading.
    // Expectation: The hashes, the emphasis markers, and a closing colon
    //   are removed, and a colon inside the label stays. A line that is
    //   not a heading has no label.
    expect(readSectionHeadingLabel(markdown)).toBe(label);
  });
});
