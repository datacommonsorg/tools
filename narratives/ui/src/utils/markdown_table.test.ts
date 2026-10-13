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
  analyzeMarkdownTable,
  citationsIn,
  type MarkdownNode,
  textOf,
} from './markdown_table';

function text(value: string): MarkdownNode {
  return { type: 'text', value };
}

function el(tagName: string, children: MarkdownNode[]): MarkdownNode {
  return { type: 'element', tagName, children };
}

function cell(tagName: 'th' | 'td', value: string): MarkdownNode {
  return el(tagName, [text(value)]);
}

/** A table shaped like the ones the agent emits: labels left, series right. */
function seriesTable(rows: [string, string][]): MarkdownNode {
  return el('table', [
    el('thead', [
      el('tr', [cell('th', 'Year'), cell('th', 'Life Expectancy (Years)')]),
    ]),
    el(
      'tbody',
      rows.map(([year, value]) =>
        el('tr', [cell('td', year), cell('td', value)]),
      ),
    ),
  ]);
}

describe('textOf', () => {
  it('reads through nested markup', () => {
    // Test: Text extraction from a cell the agent bolded.
    // Situation: A cell whose value sits inside <strong>, with the citation
    //   marker outside it.
    // Expectation: The whole cell's text, in order.
    const bolded = el('td', [el('strong', [text('84.04')]), text(' [1]')]);
    expect(textOf(bolded)).toBe('84.04 [1]');
  });

  it('is empty for a missing cell', () => {
    // Test: A ragged row.
    // Situation: The column index is past the end of the row.
    // Expectation: An empty string rather than a crash.
    expect(textOf(undefined)).toBe('');
  });
});

describe('citationsIn', () => {
  it('finds every marker, in order', () => {
    // Test: Marker extraction.
    // Situation: Text with separated and adjacent markers.
    // Expectation: Every number, in the order written.
    expect(citationsIn('a [2] b [1][3]')).toEqual([2, 1, 3]);
    expect(citationsIn('no markers')).toEqual([]);
  });
});

describe('analyzeMarkdownTable', () => {
  it('sets a column of measurements right', () => {
    // Test: Alignment of a value column.
    // Situation: A two-column time series.
    // Expectation: The value column is numeric.
    const { numericColumns } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04'],
        ['2022', '83.99'],
      ]),
    );
    expect(numericColumns.has(1)).toBe(true);
  });

  it('leaves a column of years left', () => {
    // Test: The row-label exception.
    // Situation: The first column holds bare years.
    // Expectation: Not numeric -- setting it right would push the labels away
    //   from the values they label.
    const { numericColumns } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04'],
        ['2022', '83.99'],
      ]),
    );
    expect(numericColumns.has(0)).toBe(false);
  });

  it('leaves a column of names left', () => {
    // Test: Alignment with a text label column.
    // Situation: Place names beside values.
    // Expectation: Only the value column is numeric.
    const { numericColumns } = analyzeMarkdownTable(
      el('table', [
        el('thead', [el('tr', [cell('th', 'Place'), cell('th', 'Value')])]),
        el('tbody', [
          el('tr', [cell('td', 'Japan'), cell('td', '84.04')]),
          el('tr', [cell('td', 'Italy'), cell('td', '83.51')]),
        ]),
      ]),
    );
    expect(numericColumns.has(0)).toBe(false);
    expect(numericColumns.has(1)).toBe(true);
  });

  it('tolerates a placeholder among the figures', () => {
    // Test: A gap in the series.
    // Situation: One row reports "N/A".
    // Expectation: The column is still a column of figures.
    const { numericColumns } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04'],
        ['2022', 'N/A'],
        ['2021', '84.45'],
      ]),
    );
    expect(numericColumns.has(1)).toBe(true);
  });

  it("lifts one column's shared citation onto its header", () => {
    // Test: The per-series reference.
    // Situation: Every row of the value column cites [1].
    // Expectation: The citation is hoisted, so it can be stated once on the
    //   header that names the series.
    const { hoistedCitations } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04 [1]'],
        ['2022', '83.99 [1]'],
        ['2021', '84.45 [1]'],
      ]),
    );
    expect(hoistedCitations.get(1)).toEqual([1]);
  });

  it('hoists past a placeholder row', () => {
    // Test: A gap in a single-source series.
    // Situation: One year reports "N/A" and so carries no marker.
    // Expectation: The column still hoists -- a placeholder says nothing
    //   about which source the series came from.
    const { hoistedCitations } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04 [1]'],
        ['2022', 'N/A'],
        ['2021', '84.45 [1]'],
      ]),
    );
    expect(hoistedCitations.get(1)).toEqual([1]);
  });

  it('keeps per-row markers when the rows cite different sources', () => {
    // Test: A column with mixed provenance.
    // Situation: Two of three rows cite [1] and one cites [2].
    // Expectation: No hoist -- doing it would attribute two figures to a
    //   source that did not supply them.
    const { hoistedCitations } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04 [1]'],
        ['2022', '83.99 [2]'],
        ['2021', '84.45 [1]'],
      ]),
    );
    expect(hoistedCitations.has(1)).toBe(false);
  });

  it('still finds the column numeric once the markers are off', () => {
    // Test: Interaction between the two analyses.
    // Situation: Cells carry both a figure and a marker.
    // Expectation: The marker does not disqualify the column from alignment.
    const { numericColumns } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04 [1]'],
        ['2022', '83.99 [1]'],
      ]),
    );
    expect(numericColumns.has(1)).toBe(true);
  });

  it('reads rows sitting directly under the table', () => {
    // Test: A table without a tbody.
    // Situation: Bare <tr> elements under <table>.
    // Expectation: Read as body rows -- a bare row has no header semantics.
    const { numericColumns } = analyzeMarkdownTable(
      el('table', [
        el('tr', [cell('td', 'Japan'), cell('td', '84.04')]),
        el('tr', [cell('td', 'Italy'), cell('td', '83.51')]),
      ]),
    );
    expect(numericColumns.has(1)).toBe(true);
  });

  it('says nothing about a table with no body', () => {
    // Test: A header-only table.
    // Situation: A thead and no rows beneath it.
    // Expectation: No columns classified either way.
    const empty = analyzeMarkdownTable(
      el('table', [el('thead', [el('tr', [cell('th', 'Year')])])]),
    );
    expect(empty.numericColumns.size).toBe(0);
    expect(empty.hoistedCitations.size).toBe(0);
  });

  it('says nothing when there is no table at all', () => {
    // Test: A missing node.
    // Situation: react-markdown did not supply the node.
    // Expectation: An empty analysis rather than a crash.
    const empty = analyzeMarkdownTable(undefined);
    expect(empty.numericColumns.size).toBe(0);
    expect(empty.hoistedCitations.size).toBe(0);
  });
});
