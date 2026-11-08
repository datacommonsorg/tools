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
import { createElement } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { CitationsList, citationLead } from '@/src/components/list_citations';
import type { ProvenanceItem } from '@/src/hooks/use_sse_chat';

const FULL: ProvenanceItem = {
  name: 'World Development Indicators',
  url: 'https://datatopics.worldbank.org/world-development-indicators',
  provider: 'World Bank',
  dataset: 'World Development Indicators',
  dateRange: '1960 – 2023',
  variableDcid: 'Amount_EconomicActivity_GrossDomesticProduction_Nominal',
  variableName: 'GDP (current US$)',
};

describe('citationLead', () => {
  it('names the variable, the provider, the dataset and the years', () => {
    // Test: The citation lead format.
    // Situation: The data plane reported every field.
    // Expectation: Variable, publisher, dataset and the parenthesized range,
    //   in that order, each separated by a comma.
    expect(citationLead(FULL)).toBe(
      'GDP (current US$), World Bank, World Development Indicators, ' +
        '(1960 – 2023)',
    );
  });

  it('names the variable by its DCID when it has no name', () => {
    // Test: The variable label fallback.
    // Situation: The server sent the variable DCID but no name.
    // Expectation: The DCID stands in for the name at the start of the lead.
    const { variableName: _dropped, ...unnamed } = FULL;
    expect(citationLead(unnamed)).toBe(
      'Amount_EconomicActivity_GrossDomesticProduction_Nominal, ' +
        'World Bank, World Development Indicators, (1960 – 2023)',
    );
  });

  it('falls back to the display name when the dataset is unnamed', () => {
    // Test: A source described only by name.
    // Situation: No provider, dataset, variable or range.
    // Expectation: The name alone, rather than an empty lead.
    expect(citationLead({ name: 'GHO', url: 'https://who.int' })).toBe('GHO');
  });

  it('drops the items the source did not report', () => {
    // Test: Missing fields.
    // Situation: Provider and dataset but no variable and no dates.
    // Expectation: No empty item and no empty parentheses.
    const {
      dateRange: _range,
      variableDcid: _dcid,
      variableName: _name,
      ...bare
    } = FULL;
    expect(citationLead(bare)).toBe('World Bank, World Development Indicators');
  });

  it('does not repeat a name that is really the URL', () => {
    // Test: The data plane reported neither a provider nor a dataset.
    // Situation: `name` fell back to the URL, which the link already shows.
    // Expectation: Only the range, with no leading separator and no repeat.
    expect(
      citationLead({
        name: 'https://who.int',
        url: 'https://who.int',
        dateRange: '1960 – 2023',
      }),
    ).toBe('(1960 – 2023)');
  });

  it('ignores stray whitespace when comparing the two fields', () => {
    // Test: Near-duplicate labels.
    // Situation: The same publisher arrives with a trailing space on one
    //   field.
    // Expectation: Said once, not "World Bank, World Bank ".
    expect(
      citationLead({
        name: 'World Bank',
        url: 'https://worldbank.org',
        provider: 'World Bank ',
        dataset: ' World Bank',
      }),
    ).toBe('World Bank');
  });

  it('does not say the same thing twice', () => {
    // Test: Duplicate provider and dataset.
    // Situation: Some imports report one string in both fields.
    // Expectation: Said once -- "OECD, OECD" reads as a rendering bug rather
    //   than an attribution.
    expect(
      citationLead({
        name: 'OECD',
        url: 'https://oecd.org',
        provider: 'OECD',
        dataset: 'OECD',
      }),
    ).toBe('OECD');
  });
});

describe('CitationsList', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders a row with the variable first and the full URL as its link', () => {
    // Test: One rendered citation row.
    // Situation: A source with every field and a URL with a scheme.
    // Expectation: The row reads lead (starting with the variable), URL, and
    //   the processing note joined by commas with no parentheses around the
    //   URL, and the link shows the URL in full, scheme included, and opens
    //   in a new tab.
    render(createElement(CitationsList, { sources: [FULL] }));

    const link = screen.getByRole('link', { name: FULL.url });
    expect(link.getAttribute('href')).toBe(FULL.url);
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(screen.getByRole('listitem').textContent).toBe(
      '[1]GDP (current US$), World Bank, World Development Indicators, ' +
        `(1960 – 2023), ${FULL.url}, with minor processing by Data Commons`,
    );
  });

  it('renders one row per variable of one source', () => {
    // Test: Per-variable citations of one data source.
    // Situation: Two sources share every field but the variable.
    // Expectation: Two rows, each naming its own variable.
    const perCapita: ProvenanceItem = {
      ...FULL,
      variableDcid: 'Amount_EconomicActivity_GrossDomesticProduction_PerCapita',
      variableName: 'GDP per capita',
    };
    render(createElement(CitationsList, { sources: [FULL, perCapita] }));

    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('GDP (current US$)');
    expect(rows[1].textContent).toContain('GDP per capita');
  });
});
