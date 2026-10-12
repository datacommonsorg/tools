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
  rehypeStreamWords,
  type StreamNode,
  streamDurationMs,
} from './rehype_stream_words';

const text = (value: string): StreamNode => ({ type: 'text', value });
const element = (tagName: string, children: StreamNode[]): StreamNode => ({
  type: 'element',
  tagName,
  properties: {},
  children,
});

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
});

describe('streamDurationMs', () => {
  it('grows with the answer and stops at the cap', () => {
    // Test: Reveal duration.
    // Situation: A two-word answer and a very long one.
    // Expectation: The short one takes 20ms a word; the long one is capped.
    expect(streamDurationMs('two words')).toBe(40);
    expect(streamDurationMs('word '.repeat(1000))).toBe(3000);
  });
});
