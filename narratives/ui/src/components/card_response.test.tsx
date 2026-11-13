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

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResponseCard } from '@/src/components/card_response';
import type { ProvenanceItem } from '@/src/hooks/use_sse_chat';

/**
 * The table work only holds together if react-markdown really does hand each
 * row its cells as elements this component can index, so these render the
 * whole markdown path rather than unit-testing the analysis alone.
 */

const SOURCES: ProvenanceItem[] = [
  { name: 'World Development Indicators', url: 'https://worldbank.org/wdi' },
];

const TWO_SOURCES: ProvenanceItem[] = [
  { name: 'CDC PLACES', url: 'https://www.cdc.gov/places' },
  { name: 'American Community Survey', url: 'https://www.census.gov/acs' },
];

const TABLE = `
| Year | Life Expectancy (Years) |
| --- | --- |
| 2023 | 84.0412195122 [1] |
| 2022 | 83.9963414634 [1] |
| 2021 | 84.4456097561 [1] |
`;

function renderMarkdown(body: string) {
  return render(<ResponseCard title="q" body={body} sources={SOURCES} bare />);
}

/**
 * Renders `body` with word streaming on (`streamMs`), citing the two sources
 * in `TWO_SOURCES`. `revealing` is passed through to `ResponseCard`;
 * `undefined` keeps its default.
 */
function renderStreamingMarkdown(body: string, revealing?: boolean) {
  return render(
    <ResponseCard
      title="q"
      body={body}
      sources={TWO_SOURCES}
      bare
      streamMs={300}
      revealing={revealing}
    />,
  );
}

/** Returns the `href` of every anchor under `root`, in document order. */
function getAnchorHrefs(root: Element): (string | null)[] {
  return Array.from(root.querySelectorAll('a')).map((anchor) =>
    anchor.getAttribute('href'),
  );
}

afterEach(cleanup);

describe('ResponseCard tables', () => {
  const INCOME_TABLE = `
| City | Median household income (USD, 2024) [1] |
| --- | --- |
| Austin | 93,658 |
`;

  it.each([
    ['as one string', renderMarkdown],
    ['with each word revealed', renderStreamingMarkdown],
  ])('keeps a header ending with its citation %s', (_, renderBody) => {
    // Test: A wrapping column header.
    // Situation: The header "Median household income (USD, 2024) [1]",
    //   rendered statically and with the word-by-word reveal.
    // Expectation: The spaces inside "(USD, 2024) [1]" never break, while
    //   the space before it still can, so the unit, year, and citation
    //   wrap as one word.
    const { container } = renderBody(INCOME_TABLE);
    const header = container.querySelectorAll('th')[1];
    const text = header.textContent ?? '';
    expect(text).toContain('income (USD,\u00A02024)\u00A0');
    expect(text).not.toContain('income\u00A0(');
  });
  it('caps the figures at two decimals', () => {
    // Test: Rounding inside a rendered table.
    // Situation: A time series written to eleven decimals.
    // Expectation: The two-decimal form is shown and the long one is gone.
    renderMarkdown(TABLE);
    expect(screen.getByText('84.04')).toBeTruthy();
    expect(screen.queryByText('84.0412195122')).toBeNull();
  });

  it('keeps the unrounded value reachable on the shortened figure', () => {
    // Test: Nothing is lost to rounding.
    // Situation: A figure the renderer shortened.
    // Expectation: Visually-hidden text carries the full value, so a reader
    //   who cannot hover can still check it against the source.
    const { container } = renderMarkdown(TABLE);
    const shortened = container.querySelector('.dc-numeric');
    expect(shortened?.querySelector('.sr-only')?.textContent).toBe(
      '84.04, full value 84.0412195122',
    );
  });

  it('sets the column of figures right and leaves the years left', () => {
    // Test: Column alignment.
    // Situation: A year column beside a value column.
    // Expectation: Only the values are set right.
    const { container } = renderMarkdown(TABLE);
    const firstRow = container.querySelectorAll('tbody tr')[0];
    const cells = firstRow.querySelectorAll('td');
    expect(cells[0].classList.contains('text-right')).toBe(false);
    expect(cells[1].classList.contains('text-right')).toBe(true);
  });

  it("states the column's citation once, on its header", () => {
    // Test: The per-series reference.
    // Situation: Every row of the value column cites [1].
    // Expectation: The marker appears on the header and on no body cell.
    const { container } = renderMarkdown(TABLE);
    const header = container.querySelectorAll('thead th')[1];
    expect(header.textContent).toContain('[1]');
    for (const cell of Array.from(container.querySelectorAll('tbody td'))) {
      expect(cell.textContent).not.toContain('[1]');
    }
  });

  it('strips a hoisted marker that sits inside bold', () => {
    // Test: The marker nested in markup rather than a direct text child.
    // Situation: Each cell is written as `**84.04 [1]**`.
    // Expectation: The header carries [1] and no body cell repeats it.
    const { container } = renderMarkdown(`
| Year | Life Expectancy |
| --- | --- |
| 2023 | **84.0412195122 [1]** |
| 2022 | **83.9963414634 [1]** |
`);
    expect(container.querySelectorAll('thead th')[1].textContent).toContain(
      '[1]',
    );
    for (const cell of Array.from(container.querySelectorAll('tbody td'))) {
      expect(cell.textContent).not.toContain('[1]');
    }
  });

  it('leaves per-row markers alone when rows cite different sources', () => {
    // Test: A column with mixed provenance.
    // Situation: One row cites [1] and the next cites [2].
    // Expectation: The markers stay on the rows and the header gains none.
    const { container } = renderMarkdown(`
| Year | Value |
| --- | --- |
| 2023 | 84.04 [1] |
| 2022 | 83.99 [2] |
`);
    const header = container.querySelectorAll('thead th')[1];
    expect(header.textContent).not.toContain('[1]');
    expect(container.querySelectorAll('tbody td')[1].textContent).toContain(
      '[1]',
    );
  });

  it('respects an alignment the markdown asked for', () => {
    // Test: Explicit GFM alignment.
    // Situation: The table declares centered columns.
    // Expectation: The declared alignment wins over the numeric default.
    const { container } = renderMarkdown(`
| Year | Value |
| :---: | :---: |
| 2023 | 84.0412195122 |
`);
    const cells = container.querySelectorAll<HTMLTableCellElement>('tbody td');
    expect(cells[1].style.textAlign).toBe('center');
  });
});

describe('ResponseCard prose', () => {
  it('shortens a long decimal in a sentence', () => {
    // Test: Rounding outside a table.
    // Situation: A bolded figure in running text.
    // Expectation: The two-decimal form is shown.
    renderMarkdown('Life expectancy is **84.0412195122** years [1].');
    expect(screen.getByText('84.04')).toBeTruthy();
  });

  it('compacts a figure in the millions', () => {
    // Test: Compaction outside a table.
    // Situation: A population figure with nine digits.
    // Expectation: The compact form is shown.
    renderMarkdown('The population is 125416877 people.');
    expect(screen.getByText('125.42M')).toBeTruthy();
  });

  it('leaves a year in prose alone', () => {
    // Test: The year exception in running text.
    // Situation: A sentence opening on a year.
    // Expectation: The year is unchanged.
    const { container } = renderMarkdown('As of 2023, the figure held.');
    expect(container.textContent).toContain('As of 2023');
  });

  it('shortens numbers on both sides of a citation marker', () => {
    // Test: Keys across separately rendered runs.
    // Situation: Two figures split by a citation marker, so each run is
    //   rendered separately and the pieces end up siblings in one array.
    // Expectation: Both are shortened and React reports no duplicate key.
    const consoleError = vi.spyOn(console, 'error').mockReturnValue(undefined);
    const { container } = renderMarkdown(
      'It rose from 82.8426829268 [1] to 84.0412195122 [1] over the decade.',
    );
    expect(container.textContent).toContain('82.84');
    expect(container.textContent).toContain('84.04');
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

describe('ResponseCard streaming', () => {
  it('keeps its words in place when the card renders again', () => {
    // Test: The reveal plays once.
    // Situation: A streaming answer is rendered, then rendered again with
    //   nothing changed, as happens whenever the turn around it updates.
    // Expectation: The same DOM nodes are still there. A replaced node would
    //   start its entry animation over.
    // A fresh element each time: React skips a render handed the same one.
    const card = () => (
      <ResponseCard
        title="q"
        body="One two three."
        sources={SOURCES}
        bare
        streamMs={300}
      />
    );
    const { container, rerender } = render(card());
    const before = container.querySelector('.stream-word');
    rerender(card());

    expect(before).not.toBeNull();
    expect(container.querySelector('.stream-word')).toBe(before);
  });
});

describe('ResponseCard streaming plain text', () => {
  it('leaves citation markers in code as written', () => {
    // Test: Code is not formatted as prose.
    // Situation: A streaming answer has `[1]` inside inline code and a code
    //   block, where every word is wrapped in a stream span.
    // Expectation: Both still read `[1]` verbatim rather than a citation chip.
    const { container } = render(
      <ResponseCard
        title="q"
        body={'Use `x[1]` here.\n\n```\ny = x[1]\n```'}
        sources={SOURCES}
        bare
        streamMs={300}
      />,
    );
    const code = Array.from(container.querySelectorAll('code'));

    expect(code.map((c) => c.textContent)).toEqual(['x[1]', 'y = x[1]\n']);
  });

  it('drops the animation class once the reveal is over', () => {
    // Test: A finished reveal does not replay in a copy of the DOM.
    // Situation: The card keeps its stream spans but is no longer revealing.
    // Expectation: The markdown-stream class is gone; the spans stay.
    const { container } = render(
      <ResponseCard
        title="q"
        body="One two."
        bare
        streamMs={300}
        revealing={false}
      />,
    );

    expect(container.querySelector('.markdown-stream')).toBeNull();
    expect(container.querySelector('.stream-word')).not.toBeNull();
  });
});

describe('ResponseCard streaming composite citations', () => {
  it.each([
    ['while revealing', undefined],
    ['after the reveal', false],
  ])('links each source of a composite marker in prose %s', (_, revealing) => {
    // Test: A composite marker in streamed prose.
    // Situation: A bold figure followed by `[1, 2].`, every word wrapped in a
    //   stream span, with `revealing` left at its default or set to false.
    // Expectation: Two links, to sources 1 and 2, each named for its source,
    //   separated by one space and followed by the period.
    const { container } = renderStreamingMarkdown(
      '**64.25%** [1, 2].',
      revealing,
    );
    const paragraph = container.querySelector('p');

    expect(container.querySelector('.stream-word')).not.toBeNull();
    expect(paragraph).not.toBeNull();
    expect(getAnchorHrefs(container)).toEqual([
      '#citation-0-1',
      '#citation-0-2',
    ]);
    expect(paragraph?.textContent).toBe('64.25% [1] [2].');
    expect(
      screen.getByRole('link', { name: 'Source 1: CDC PLACES' }),
    ).toBeTruthy();
    expect(
      screen.getByRole('link', { name: 'Source 2: American Community Survey' }),
    ).toBeTruthy();
  });

  it('links only the sources a composite marker can cite', () => {
    // Test: A composite marker naming a source past the provenance list.
    // Situation: `[1, 9]` is streamed against two sources.
    // Expectation: `[1]` is a link and `[9]` is plain text.
    const { container } = renderStreamingMarkdown('The rate rose [1, 9].');

    expect(container.querySelector('.stream-word')).not.toBeNull();
    expect(getAnchorHrefs(container)).toEqual(['#citation-0-1']);
    expect(container.querySelector('p')?.textContent).toBe(
      'The rate rose [1] [9].',
    );
  });

  it.each([
    ['bare', '9.47 [1, 2]', '10.12 [1, 2]'],
    ['bold', '**64.25% [1, 2]**', '**71.5% [1, 2]**'],
  ])('hoists a composite marker off a %s value column', (_, firstCell, secondCell) => {
    // Test: A table column whose every cell cites the same two sources.
    // Situation: Each value cell ends in `[1, 2]`, streamed word by word.
    // Expectation: The header links to sources 1 and 2, the value cells are
    //   right-aligned with tabular numerals, and no body cell keeps the
    //   marker or a fragment of it.
    const { container } = renderStreamingMarkdown(`
| County | Diabetes rate |
| --- | --- |
| Coos | ${firstCell} |
| Grafton | ${secondCell} |
`);
    const header = container.querySelectorAll('thead th')[1];
    const bodyCells = Array.from(
      container.querySelectorAll<HTMLTableCellElement>('tbody td'),
    );
    const valueCells = bodyCells.filter((_, index) => index % 2 === 1);

    expect(container.querySelector('.stream-word')).not.toBeNull();
    expect(getAnchorHrefs(header)).toEqual(['#citation-0-1', '#citation-0-2']);
    for (const cell of valueCells) {
      expect(cell.classList.contains('text-right')).toBe(true);
      expect(cell.classList.contains('tabular-nums')).toBe(true);
    }
    for (const cell of bodyCells) {
      for (const fragment of ['[1]', '[2]', '[1,', '2]']) {
        expect(cell.textContent).not.toContain(fragment);
      }
    }
  });

  it('leaves composite markers in code as written', () => {
    // Test: Code is not formatted as prose.
    // Situation: `[1, 2]` sits in inline code and in a code block, and a
    //   bracket expression spans several lines of the code block.
    // Expectation: The code reads exactly as written and holds no links.
    const { container } = renderStreamingMarkdown(
      'Use `x[1, 2]` here.\n\n```\ny = x[1, 2]\nz = [\n  1,\n  2\n]\n```',
    );
    const codeElements = Array.from(container.querySelectorAll('code'));

    expect(codeElements.map((codeElement) => codeElement.textContent)).toEqual([
      'x[1, 2]',
      'y = x[1, 2]\nz = [\n  1,\n  2\n]\n',
    ]);
    expect(container.querySelectorAll('code a')).toHaveLength(0);
  });

  it('leaves a composite marker in link text as written', () => {
    // Test: Link text is not formatted as prose.
    // Situation: The text of a markdown link contains `[1, 2]`.
    // Expectation: The link is the only anchor and its text is unchanged.
    const { container } = renderStreamingMarkdown(
      '[see [1, 2]](https://example.com)',
    );

    expect(getAnchorHrefs(container)).toEqual(['https://example.com']);
    expect(container.querySelector('a')?.textContent).toBe('see [1, 2]');
  });
});

describe('ResponseCard headings', () => {
  it('ranks markdown headings one level below the intro h1', () => {
    // Test: Heading levels.
    // Situation: Markdown headings from `#` to `####`.
    // Expectation: They render as h2 to h5; the answer holds no h1.
    const { container } = renderMarkdown('# A\n\n## B\n\n### C\n\n#### D');

    expect(container.querySelector('h1')).toBeNull();
    expect(
      ['h2', 'h3', 'h4', 'h5'].map(
        (tag) => container.querySelector(tag)?.textContent,
      ),
    ).toEqual(['A', 'B', 'C', 'D']);
  });
});

describe('ResponseCard bold-only paragraphs', () => {
  it('renders a paragraph of only bold text as a subheading', () => {
    // Test: Bold-only paragraphs.
    // Situation: One paragraph is all bold, streamed word by word; another
    //   mixes bold with plain text.
    // Expectation: The first becomes an h3, with no strong inside; the second
    //   stays a paragraph with its strong.
    const { container } = renderStreamingMarkdown(
      '**Ten highest-income places:**\n\nThe **top** one leads.',
    );
    const heading = container.querySelector('h3');

    expect(heading?.textContent).toBe('Ten highest-income places:');
    expect(heading?.querySelector('strong')).toBeNull();
    expect(container.querySelector('p strong')?.textContent).toBe('top');
  });

  it('keeps bold items of a loose list and a blockquote as emphasis', () => {
    // Test: Nested bold-only paragraphs.
    // Situation: A loose list, whose items are wrapped in paragraphs, and a
    //   blockquote, each holding only bold text.
    // Expectation: No subheading is made; the bold stays a strong in a
    //   paragraph.
    const { container } = renderMarkdown(
      '- **Total**\n\n- **Average**\n\n> **Note**',
    );

    expect(container.querySelector('h3')).toBeNull();
    expect(
      Array.from(container.querySelectorAll('p > strong')).map(
        (strong) => strong.textContent,
      ),
    ).toEqual(['Total', 'Average', 'Note']);
  });
});
