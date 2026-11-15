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
  isBoldOnlyParagraph,
  type MarkdownNode,
  splitHeaderTail,
  textOf,
} from '@/src/utils/markdown_table';

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

describe('isBoldOnlyParagraph', () => {
  it('is true for a lone bold line, whitespace aside', () => {
    // Test: The model's stand-in for a heading.
    // Situation: `**Plan**` with surrounding whitespace text nodes.
    // Expectation: Recognized as a bold-only paragraph.
    const p = el('p', [text('\n'), el('strong', [text('Plan')]), text(' ')]);
    expect(isBoldOnlyParagraph(p)).toBe(true);
  });

  it('is false when bold sits beside other text', () => {
    // Test: Inline emphasis.
    // Situation: A bold lead-in followed by prose.
    // Expectation: An ordinary paragraph.
    const p = el('p', [el('strong', [text('Note:')]), text(' rates rose.')]);
    expect(isBoldOnlyParagraph(p)).toBe(false);
  });

  it('is false for a missing node', () => {
    expect(isBoldOnlyParagraph(undefined)).toBe(false);
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

  it('reads every number of a composite marker', () => {
    // Test: Composite marker extraction.
    // Situation: A derived figure cites two sources as `[1, 2]`, followed by
    //   a single marker.
    // Expectation: Both numbers of the composite marker, then the single one.
    expect(citationsIn('**64.25%** [1, 2] and [3]')).toEqual([1, 2, 3]);
  });
});

describe('splitHeaderTail', () => {
  it('keeps a short unit and year with the marker after it', () => {
    // Test: The ending of a column header that wraps.
    // Situation: A header ending in "($, 2024) [1]".
    // Expectation: The parenthetical and its marker form the unbroken
    //   ending; the words before it may wrap.
    expect(splitHeaderTail('Median household income ($, 2024) [1]')).toEqual([
      'Median household income ',
      '($, 2024) [1]',
    ]);
  });

  it('keeps only the last word of a long parenthetical with the marker', () => {
    // Test: A parenthetical too long to hold on one line.
    // Situation: "(deaths per 100,000 live births, 2020)" before a marker.
    // Expectation: Only its last word stays with the marker, so a narrow
    //   column is not forced wider.
    expect(
      splitHeaderTail(
        'Maternal mortality (deaths per 100,000 live births, 2020) [3]',
      ),
    ).toEqual([
      'Maternal mortality (deaths per 100,000 live births, ',
      '2020) [3]',
    ]);
  });

  it('keeps the last word with a composite marker', () => {
    // Test: A header without a parenthetical.
    // Situation: "Population 2024 [1, 2]".
    // Expectation: The last word and the composite marker stay together.
    expect(splitHeaderTail('Population 2024 [1, 2]')).toEqual([
      'Population ',
      '2024 [1, 2]',
    ]);
  });

  it('leaves a one-word header whole', () => {
    // Test: Nothing to split.
    // Situation: The header "Rank".
    // Expectation: The whole text, with an empty ending.
    expect(splitHeaderTail('Rank')).toEqual(['Rank', '']);
  });
});

describe('analyzeMarkdownTable', () => {
  it('finds a column headed "Rank" so it can be centered', () => {
    // Test: Detection of a rank column.
    // Situation: A ranking table headed `rank`, `State`, and a value column,
    //   the rank header in lower case.
    // Expectation: Only the first column is a rank column.
    const table = el('table', [
      el('thead', [
        el('tr', [
          cell('th', 'rank'),
          cell('th', 'State'),
          cell('th', 'Unemployment rate (%, 2024) [1]'),
        ]),
      ]),
      el('tbody', [
        el('tr', [cell('td', '1'), cell('td', 'Nevada'), cell('td', '5.6')]),
        el('tr', [
          cell('td', '2'),
          cell('td', 'California'),
          cell('td', '5.4'),
        ]),
      ]),
    ]);
    const { rankColumns } = analyzeMarkdownTable(table);
    expect([...rankColumns]).toEqual([0]);
  });

  it('finds no rank column in a table without one', () => {
    // Test: Tables without a rank column.
    // Situation: A two-column time series.
    // Expectation: No rank column.
    const { rankColumns } = analyzeMarkdownTable(
      seriesTable([
        ['2023', '84.04'],
        ['2022', '83.99'],
      ]),
    );
    expect(rankColumns.size).toBe(0);
  });
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

  it('hoists a shared composite marker and keeps the column numeric', () => {
    // Test: Composite per-series citations in a value column.
    // Situation: Every row of a derived value column cites `[1, 2]`.
    // Expectation: Both source numbers hoist onto the header in order and
    //   stripping the composite marker leaves the column numeric.
    const analysis = analyzeMarkdownTable(
      seriesTable([
        ['2023', '64.25% [1, 2]'],
        ['2022', '63.80% [1, 2]'],
      ]),
    );
    expect(analysis.hoistedCitations.get(1)).toEqual([1, 2]);
    expect(analysis.numericColumns.has(1)).toBe(true);
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
