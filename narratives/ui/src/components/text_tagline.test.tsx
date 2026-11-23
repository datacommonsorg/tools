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
 * @fileoverview Tests for TaglineText.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TaglineText } from '@/src/components/text_tagline';
import type { TaglineLink } from '@/src/config/instance_config';

const TAGLINE = 'Data in the Knowledge Graph';

const LINK: TaglineLink = {
  text: 'Knowledge Graph',
  sections: [
    { title: 'About the graph', body: 'Graph description.' },
    { title: 'About this tool', body: 'Tool description.' },
  ],
  sources: { label: 'See sources', href: 'https://example.org/sources' },
};

/** Renders the tagline, opens the dialog from its phrase, and returns it. */
const renderOpenDialog = (link: TaglineLink): HTMLDialogElement => {
  render(<TaglineText tagline={TAGLINE} link={link} />);
  fireEvent.click(screen.getByRole('button', { name: link.text }));
  return screen.getByRole('dialog') as HTMLDialogElement;
};

afterEach(cleanup);

describe('TaglineText', () => {
  it('opens the dialog from the linked phrase', () => {
    // Test: Tagline containing the configured link phrase.
    // Situation: The phrase is clicked.
    // Expectation: The dialog opens with the configured sections, named by
    //   the first title, and light dismiss (`closedby="any"`) lets a backdrop
    //   click close it.
    const dialog = renderOpenDialog(LINK);
    expect(dialog.open).toBe(true);
    expect(screen.getByRole('dialog', { name: 'About the graph' })).toBe(
      dialog,
    );
    expect(dialog.textContent).toContain('Graph description.');
    expect(dialog.textContent).toContain('About this tool');
    expect(dialog.textContent).toContain('Tool description.');
    expect(dialog.getAttribute('closedby')).toBe('any');
  });

  it('links to the sources and closes from the action bar', () => {
    // Test: Dialog action bar.
    // Situation: The dialog is opened, then "Got it" is clicked.
    // Expectation: The sources link opens its URL in a new tab, and
    //   "Got it" closes the dialog.
    const dialog = renderOpenDialog(LINK);
    const sources = screen.getByRole('link', { name: 'See sources' });
    expect(sources.getAttribute('href')).toBe('https://example.org/sources');
    expect(sources.getAttribute('target')).toBe('_blank');

    fireEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(dialog.open).toBe(false);
  });

  it('shows only "Got it" when no sources link is configured', () => {
    // Test: Tagline link without `sources`.
    // Situation: The dialog is opened from a link that has no sources.
    // Expectation: The action bar has no link, only the "Got it" button.
    const { sources: _, ...linkWithoutSources } = LINK;
    renderOpenDialog(linkWithoutSources);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByRole('button', { name: 'Got it' })).not.toBeNull();
  });

  it.each([
    ['the phrase is absent', 'Custom tagline', LINK],
    ['the phrase is empty', 'Custom tagline', { ...LINK, text: '' }],
  ])('renders plain text when %s', (_, tagline, link) => {
    // Test: Tagline that cannot carry the link.
    // Situation: The tagline does not contain `link.text`, or `link.text` is
    //   empty.
    // Expectation: The text renders with no button and no dialog.
    render(<TaglineText tagline={tagline} link={link} />);
    expect(screen.getByText(tagline)).not.toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('dialog', { hidden: true })).toBeNull();
  });
});
