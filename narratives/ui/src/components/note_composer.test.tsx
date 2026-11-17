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
import { afterEach, describe, expect, it } from 'vitest';
import {
  COMPOSER_DISCLAIMER_TEXT,
  ComposerNote,
  POLICY_LINKS,
} from '@/src/components/note_composer';

afterEach(cleanup);

describe('ComposerNote', () => {
  it('shows the disclaimer wording', () => {
    // Test: The disclaimer text under the prompt box.
    // Situation: The note renders.
    // Expectation: The approved wording is present.
    const { container } = render(<ComposerNote />);
    expect(container.textContent).toContain(COMPOSER_DISCLAIMER_TEXT);
  });

  it.each(
    Object.values(POLICY_LINKS),
  )('links $label in a new tab, underlined', ({ label, href }) => {
    // Test: Each Google policy link.
    // Situation: The note renders.
    // Expectation: The link points at the policy, opens in a new tab
    //   without an opener, and is underlined so it does not rely on color
    //   alone.
    render(<ComposerNote />);
    const link = screen.getByRole('link', { name: label });
    expect(link.getAttribute('href')).toBe(href);
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(link.classList).toContain('underline');
  });
});
