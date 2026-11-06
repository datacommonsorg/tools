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
 * @fileoverview Tests the rehype plugin that staggers an answer's words.
 */

import { describe, expect, it } from 'vitest';
import {
  calculateStreamDurationMs,
  countWords,
  rehypeStreamWords,
  type StreamNode,
} from '@/src/utils/rehype_stream_words';

const text = (value: string): StreamNode => ({ type: 'text', value });
const element = (tagName: string, children: StreamNode[]): StreamNode => ({
  type: 'element',
  tagName,
  properties: {},
  children,
});

/** Concatenates every text value under `node`, in document order. */
const readText = (node: StreamNode): string => {
  if (node.type === 'text') return node.value ?? '';
  return (node.children ?? []).map(readText).join('');
};

/** Streams a one-paragraph tree of `value` and returns its word spans. */
const streamParagraph = (value: string): StreamNode[] => {
  const paragraph = element('p', [text(value)]);
  rehypeStreamWords(100)(element('root', [paragraph]));
  return (paragraph.children ?? []).filter((node) => node.tagName === 'span');
};

describe('rehypeStreamWords', () => {
  it('delays each word in reading order and keeps the text intact', () => {
    // Test: Word staggering.
    // Situation: A paragraph is followed by a list item, five words in all,
    //   revealed over 500ms.
    // Expectation: Words are wrapped with delays 100ms apart, whitespace
    //   stays plain text, and the list item waits for its first word.
    const item = element('li', [text('three four')]);
    const tree = element('root', [
      element('p', [text('one '), element('strong', [text('two [1]')])]),
      element('ul', [item]),
    ]);

    rehypeStreamWords(500)(tree);

    const delays: unknown[] = [];
    const read = (node: StreamNode): string => {
      if (node.type === 'text') return node.value ?? '';
      if (node.tagName === 'span') delays.push(node.properties?.style);
      return (node.children ?? []).map(read).join('');
    };
    expect(read(tree)).toBe('one two [1]three four');
    expect(delays).toEqual([
      'animation-delay:0ms',
      'animation-delay:100ms',
      'animation-delay:200ms',
      'animation-delay:300ms',
      'animation-delay:400ms',
    ]);
    expect(item.properties?.style).toBe('animation-delay:300ms');
  });

  it("keeps a container's existing inline style", () => {
    // Test: Container with an inline style.
    // Situation: A list item already carries `color:red`.
    // Expectation: The animation delay is appended, not substituted.
    const item = element('li', [text('one')]);
    item.properties = { style: 'color:red' };

    rehypeStreamWords(100)(element('root', [item]));

    expect(item.properties?.style).toBe('color:red;animation-delay:0ms');
  });

  it('offsets every delay by the start time', () => {
    // Test: Reveal offset.
    // Situation: A two-word paragraph revealed over 100ms, starting at 300ms.
    // Expectation: The words are delayed 300ms and 350ms.
    const paragraph = element('p', [text('one two')]);

    rehypeStreamWords(100, 300)(element('root', [paragraph]));

    const delays = (paragraph.children ?? [])
      .filter((node) => node.tagName === 'span')
      .map((node) => node.properties?.style);
    expect(delays).toEqual(['animation-delay:300ms', 'animation-delay:350ms']);
  });

  it('wraps a composite citation marker in one word span', () => {
    // Test: Composite markers with two and three numbers.
    // Situation: A paragraph holds `[1, 2]`, `[1, 2, 3]`, and `[2 , 3]` after
    //   one other word, revealed over 400ms.
    // Expectation: Each marker is one span, the paragraph text is unchanged,
    //   and the four spans are delayed 100ms apart.
    const input = 'rose [1, 2] [1, 2, 3] [2 , 3]';
    const paragraph = element('p', [text(input)]);

    rehypeStreamWords(400)(element('root', [paragraph]));

    const words = (paragraph.children ?? []).filter(
      (node) => node.tagName === 'span',
    );
    expect(words.map(readText)).toEqual([
      'rose',
      '[1, 2]',
      '[1, 2, 3]',
      '[2 , 3]',
    ]);
    expect(readText(paragraph)).toBe(input);
    expect(words.map((node) => node.properties?.style)).toEqual([
      'animation-delay:0ms',
      'animation-delay:100ms',
      'animation-delay:200ms',
      'animation-delay:300ms',
    ]);
  });

  it('keeps characters attached to a composite marker in its span', () => {
    // Test: Composite markers with characters attached on either side.
    // Situation: Markers followed by a period, wrapped in parentheses, and
    //   followed by another marker.
    // Expectation: Each marker shares one span with its attached characters.
    expect(streamParagraph('rate [1, 2].').map(readText)).toEqual([
      'rate',
      '[1, 2].',
    ]);
    expect(streamParagraph('see ([1, 2]) and [1, 2][3]').map(readText)).toEqual(
      ['see', '([1, 2])', 'and', '[1, 2][3]'],
    );
  });

  it('splits a bracket expression that is not a marker on whitespace', () => {
    // Test: Bracket expressions outside the marker grammar.
    // Situation: A list spread over several lines, a composite marker broken
    //   by a line break, and brackets holding a letter.
    // Expectation: Each splits at its whitespace like any other text.
    expect(streamParagraph('[\n  1,\n  2\n]').map(readText)).toEqual([
      '[',
      '1,',
      '2',
      ']',
    ]);
    expect(streamParagraph('[1,\n2]').map(readText)).toEqual(['[1,', '2]']);
    expect(streamParagraph('[1, b]').map(readText)).toEqual(['[1,', 'b]']);
  });
});

describe('countWords', () => {
  it('counts the words rehypeStreamWords wraps', () => {
    // Test: Word count and span count agree.
    // Situation: Text holding a composite marker with attached punctuation.
    // Expectation: The count is 8 and equals the number of word spans.
    const input = 'It rose to 9.47 [1, 2]. It fell [2 , 3].';

    expect(countWords(input)).toBe(streamParagraph(input).length);
    expect(countWords(input)).toBe(8);
  });
});

describe('calculateStreamDurationMs', () => {
  it('grows with the answer and stops at the cap', () => {
    // Test: Reveal duration.
    // Situation: A two-word answer and a very long one.
    // Expectation: The short one takes 20ms a word; the long one is capped.
    expect(calculateStreamDurationMs('two words')).toBe(40);
    expect(calculateStreamDurationMs('word '.repeat(1000))).toBe(3000);
  });

  it('counts a composite citation marker as one word', () => {
    // Test: Reveal duration of text with a composite marker.
    // Situation: The text `two [1, 2]`, which streams as two word spans.
    // Expectation: The reveal takes 40ms, 20ms for each of the two words.
    expect(calculateStreamDurationMs('two [1, 2]')).toBe(40);
  });
});
