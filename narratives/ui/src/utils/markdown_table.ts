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
 * @fileoverview Reads a markdown table's AST to find its numeric columns and
 * its per-column citations.
 */

import {
  createCitationMarkerPattern,
  parseCitationNumbers,
} from '@/src/utils/citation_marker';
import {
  isNeutralText,
  isNumericText,
  isYearText,
} from '@/src/utils/format_number';

/**
 * The part of an HTML AST node this module reads. Declared locally rather
 * than imported from the `hast` types, so the analysis is testable from an
 * object literal.
 */
export interface MarkdownNode {
  type?: string;
  tagName?: string;
  value?: string;
  children?: MarkdownNode[];
}

/** What the table renderer needs to know that a single cell cannot tell it. */
export interface TableAnalysis {
  /** Columns whose body cells are all values — these are set right. */
  numericColumns: ReadonlySet<number>;
  /**
   * Citations lifted out of a column's cells onto its header. Only columns
   * whose every cell agreed, so one citing different sources per row keeps
   * its per-row markers.
   */
  hoistedCitations: ReadonlyMap<number, number[]>;
  /** Columns headed "Rank", whose short ordinal numbers are centered. */
  rankColumns: ReadonlySet<number>;
}

/** Concatenates every text node under `node`. */
export function textOf(node: MarkdownNode | undefined): string {
  if (!node) return '';
  if (typeof node.value === 'string') return node.value;
  return (node.children ?? []).map(textOf).join('');
}

/** The citation numbers in `text`, in the order they appear. */
export function citationsIn(text: string): number[] {
  const pattern = createCitationMarkerPattern();
  const out: number[] = [];
  for (const match of text.matchAll(pattern)) {
    out.push(...parseCitationNumbers(match[1]));
  }
  return out;
}

/** The longest parenthetical kept whole on one line, such as "(USD, 2025)". */
const MAX_UNBROKEN_PARENTHETICAL = 20;

/** A header's trailing citation markers, such as " [1]" or " [1, 2] [3]". */
const TRAILING_MARKERS = /(?:\s*\[\d+(?:\s*,\s*\d+)*\])*\s*$/;

/**
 * Splits a column header into the part that may wrap and the ending that
 * must not, so a citation never wraps away from the words it cites. The
 * ending is the closing parenthetical, such as "(USD, 2025)", when it is
 * short, or else the last word, together with any citation markers after
 * it: "Median household income ($, 2024) [1]" keeps "($, 2024) [1]" on one
 * line. Returns `[text, '']` when there is nothing to keep together.
 */
export function splitHeaderTail(text: string): [string, string] {
  const markers = text.match(TRAILING_MARKERS)?.[0] ?? '';
  const body = text.slice(0, text.length - markers.length);
  const parenthetical = body.match(/\([^()]*\)$/)?.[0];
  const ending =
    parenthetical && parenthetical.length <= MAX_UNBROKEN_PARENTHETICAL
      ? parenthetical
      : (body.match(/\S+$/)?.[0] ?? '');
  if (ending === '' || ending === body.trim()) return [text, ''];
  return [body.slice(0, body.length - ending.length), ending + markers];
}

/** True when `node` is an element with the given tag. */
function isTag(node: MarkdownNode, tagName: string): boolean {
  return node.type === 'element' && node.tagName === tagName;
}

/**
 * Whether a paragraph's only content, whitespace aside, is one `strong`: a
 * standalone bold line, which models write in place of a heading.
 */
export function isBoldOnlyParagraph(node: MarkdownNode | undefined): boolean {
  const content = (node?.children ?? []).filter(
    (child) => !(child.type === 'text' && !child.value?.trim()),
  );
  return content.length === 1 && isTag(content[0], 'strong');
}

/** The cells of every row in a table section, flattened past thead/tbody. */
function rowsOf(
  node: MarkdownNode,
  section: 'thead' | 'tbody',
): MarkdownNode[][] {
  const rows: MarkdownNode[][] = [];
  const collect = (row: MarkdownNode) => {
    if (!isTag(row, 'tr')) return;
    rows.push(
      (row.children ?? []).filter(
        (cell) => isTag(cell, 'td') || isTag(cell, 'th'),
      ),
    );
  };
  for (const child of node.children ?? []) {
    if (isTag(child, section)) (child.children ?? []).forEach(collect);
    // A bare <tr> under <table> has no header semantics, so it is a body row.
    else if (section === 'tbody' && isTag(child, 'tr')) collect(child);
  }
  return rows;
}

/** Matches a header that names a rank column, citation markers aside. */
const RANK_HEADER = /^rank$/i;

/**
 * Works out which columns hold values, which carry one shared citation, and
 * which are rank columns. Each answer needs the whole column, which a single
 * cell cannot see.
 */
export function analyzeMarkdownTable(
  node: MarkdownNode | undefined,
): TableAnalysis {
  const numericColumns = new Set<number>();
  const hoistedCitations = new Map<number, number[]>();
  const rankColumns = new Set<number>();
  if (!node) return { numericColumns, hoistedCitations, rankColumns };

  for (const row of rowsOf(node, 'thead')) {
    row.forEach((cell, column) => {
      const header = textOf(cell)
        .replace(createCitationMarkerPattern(), '')
        .trim();
      if (RANK_HEADER.test(header)) rankColumns.add(column);
    });
  }

  const bodyRows = rowsOf(node, 'tbody');
  if (bodyRows.length === 0) {
    return { numericColumns, hoistedCitations, rankColumns };
  }
  const columnCount = Math.max(...bodyRows.map((row) => row.length));

  for (let column = 0; column < columnCount; column++) {
    const cells = bodyRows
      .map((row) => textOf(row[column]))
      .filter((text) => text.trim() !== '');
    if (cells.length === 0) continue;

    // Citations first: the markers have to come off before the rest of the
    // cell can be judged a number.
    const values = cells.map((text) =>
      text.replace(createCitationMarkerPattern(), '').trim(),
    );
    const citations = cells
      .filter((_, i) => !isNeutralText(values[i]))
      .map(citationsIn);
    const key = citations[0]?.join(',') ?? '';
    if (
      citations.length > 0 &&
      key !== '' &&
      citations.every((list) => list.join(',') === key)
    ) {
      hoistedCitations.set(column, [...new Set(citations[0])]);
    }

    const numeric = values.filter((text) => isNumericText(text));
    const undecided = values.filter((text) => isNeutralText(text));
    const measurements = numeric.filter((text) => !isYearText(text));
    if (
      numeric.length > 0 &&
      measurements.length > 0 &&
      numeric.length + undecided.length === values.length
    ) {
      numericColumns.add(column);
    }
  }

  return { numericColumns, hoistedCitations, rankColumns };
}
