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
 * @fileoverview Provides the rehype plugin that staggers an answer's words so it reveals in reading order.
 */

import { CITATION_MARKER_PATTERN_SOURCE } from '@/src/utils/citation_marker';

/** Specifies the reveal time given to each word of an answer. */
const MS_PER_WORD = 20;
/** Specifies the longest a reveal runs, however long the answer is. */
const MAX_STREAM_MS = 3000;
/** Class of the span wrapped around each word; styled in index.css. */
export const STREAM_WORD_CLASS = 'stream-word';
/**
 * Matches a whitespace run or a word run. A word run is a maximal sequence of
 * citation markers and non-whitespace characters; the marker alternative comes
 * first so the spaces inside `[1, 2]` stay in the word.
 */
const STREAM_TOKEN_PATTERN = new RegExp(
  String.raw`(?:${CITATION_MARKER_PATTERN_SOURCE}|\S)+|\s+`,
  'g',
);
/**
 * Elements that draw something of their own (a bullet, a grid, a rule), so
 * they wait for their first word rather than showing ahead of their text.
 */
const STREAMED_CONTAINERS: ReadonlySet<string> = new Set([
  'li',
  'table',
  'hr',
  'blockquote',
]);

/** Minimal shape of the hast nodes the plugin reads and writes. */
export interface StreamNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: StreamNode[];
}

/**
 * Splits `text` into alternating whitespace runs and word runs whose
 * concatenation is `text`. A citation marker and the non-whitespace attached
 * to it, as in `[1, 2].`, form one word run.
 */
function splitStreamTokens(text: string): string[] {
  // `match` with a global pattern scans from index 0 and resets `lastIndex`,
  // so the shared pattern carries no state between calls.
  return text.match(STREAM_TOKEN_PATTERN) ?? [];
}

/** Returns true when `token` is a whitespace run. */
function isWhitespace(token: string): boolean {
  return token.trim() === '';
}

/**
 * Returns the number of words in `text`, split as {@link rehypeStreamWords}
 * splits them, so a citation marker such as `[1, 2]` counts as one word.
 */
export function countWords(text: string): number {
  return splitStreamTokens(text).filter((token) => !isWhitespace(token)).length;
}

/** Returns how long the reveal of `text` runs, in milliseconds. */
export function calculateStreamDurationMs(text: string): number {
  return Math.min(countWords(text) * MS_PER_WORD, MAX_STREAM_MS);
}

/**
 * Wraps every word in a span and gives each an `animation-delay` that grows
 * in reading order, spread across `durationMs` and offset by `startMs`, so a
 * body that follows another in one reveal starts where the previous one ends.
 * Whitespace stays as plain text so wrapping and copy-paste are unchanged.
 */
export function rehypeStreamWords(durationMs: number, startMs = 0) {
  return (tree: StreamNode): void => {
    // Each entry is a node and the index of the word it appears with.
    const timed: [StreamNode, number][] = [];
    let words = 0;
    const walk = (node: StreamNode): void => {
      if (!node.children) return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== 'text') {
          if (STREAMED_CONTAINERS.has(child.tagName ?? '')) {
            timed.push([child, words]);
          }
          walk(child);
          return [child];
        }
        return splitStreamTokens(child.value ?? '').map((part): StreamNode => {
          if (isWhitespace(part)) return { type: 'text', value: part };
          const word: StreamNode = {
            type: 'element',
            tagName: 'span',
            properties: { className: [STREAM_WORD_CLASS] },
            children: [{ type: 'text', value: part }],
          };
          timed.push([word, words++]);
          return word;
        });
      });
    };
    walk(tree);
    const step = durationMs / Math.max(words, 1);
    for (const [node, index] of timed) {
      const delay = `animation-delay:${Math.round(startMs + index * step)}ms`;
      const style = node.properties?.style;
      node.properties = {
        ...node.properties,
        style: typeof style === 'string' ? `${style};${delay}` : delay,
      };
    }
  };
}
