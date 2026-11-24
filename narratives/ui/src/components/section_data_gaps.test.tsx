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

import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { DataGapsSection } from '@/src/components/section_data_gaps';

afterEach(cleanup);

describe('DataGapsSection', () => {
  it('lists the missing measures under its heading and intro', () => {
    // Test: The section's content.
    // Situation: The section renders with an intro and two measures.
    // Expectation: A region named by its "Data gaps" h2 holds the intro
    //   and one list item per measure, in order.
    render(
      <DataGapsSection
        intro="These measures are not available in Data Commons:"
        items={['Antenatal care coverage', 'Screening coverage']}
      />,
    );

    const section = screen.getByRole('region', { name: 'Data gaps' });
    expect(within(section).getByRole('heading', { level: 2 }).textContent).toBe(
      'Data gaps',
    );
    expect(section.querySelector('p')?.textContent).toBe(
      'These measures are not available in Data Commons:',
    );
    expect(
      within(section)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['Antenatal care coverage', 'Screening coverage']);
  });

  it('renders no intro paragraph for an empty intro', () => {
    // Test: A list the model did not introduce.
    // Situation: The section renders with an empty intro.
    // Expectation: The section holds the list and no paragraph.
    render(<DataGapsSection intro="" items={['Antenatal care coverage']} />);

    const section = screen.getByRole('region', { name: 'Data gaps' });
    expect(section.querySelector('p')).toBeNull();
    expect(within(section).getAllByRole('listitem')).toHaveLength(1);
  });
});
