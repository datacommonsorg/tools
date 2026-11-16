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
  isLeadInHeading,
  readLeadInLabel,
} from '@/src/components/heading_section';

describe('isLeadInHeading', () => {
  it.each([
    ['a plain label', 'Population by sex:'],
    ['a bold label', '**Population by sex:**'],
    ['a label with trailing spaces', 'Population by sex:  '],
  ])('accepts %s', (_, markdown) => {
    // Test: Lines that render as a section heading.
    // Situation: One line with a plain label that ends with a colon,
    //   optionally in bold.
    // Expectation: It is a section heading.
    expect(isLeadInHeading(markdown)).toBe(true);
  });

  it.each([
    ['a sentence', 'The population rose.'],
    ['a list item', '- **Female:**'],
    ['a table row', '| Country: |'],
    ['a heading', '# Population:'],
    ['two lines', '**Data gaps**\\\nThese measures are missing:'],
    ['a label with a citation marker', 'Population by sex [1]:'],
    ['a label with inner bold', '**Canada** by sex:'],
    ['an empty label', '**:**'],
    ['a label with a backslash escape', 'Births \\(per 1,000\\):'],
    ['a label with an HTML entity', 'R&amp;D spending:'],
  ])('rejects %s', (_, markdown) => {
    // Test: Lines that do not render as a section heading.
    // Situation: A sentence, a list item, a table row, a heading, a
    //   paragraph of more than one line, or a lead-in whose label holds a
    //   citation marker, inline Markdown, a backslash escape, an HTML
    //   entity, or no letter or digit.
    // Expectation: It is not a section heading, so it renders as text.
    expect(isLeadInHeading(markdown)).toBe(false);
  });
});

describe('readLeadInLabel', () => {
  it.each([
    ['Population by sex:', 'Population by sex'],
    ['**Population by sex:**', 'Population by sex'],
    ['**Population by sex**:', 'Population by sex'],
    ['_Ratio: women to men:_', 'Ratio: women to men'],
  ])('reads the label of %s', (markdown, label) => {
    // Test: The heading text of a lead-in line.
    // Situation: A lead-in line, plain or wrapped in emphasis.
    // Expectation: The closing colon and the emphasis markers around it
    //   are removed; a colon inside the label stays.
    expect(readLeadInLabel(markdown)).toBe(label);
  });
});
