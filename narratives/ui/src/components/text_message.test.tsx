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
 * @fileoverview Tests for MessageText.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MessageText } from '@/src/components/text_message';

afterEach(cleanup);

describe('MessageText', () => {
  it('renders a Markdown link as a same-tab link', () => {
    // Test: Message with a Markdown link.
    // Situation: The message holds `[label](https://…)`.
    // Expectation: The label renders as a link to the URL in the same tab,
    //   with the surrounding text intact.
    const { container } = render(
      <MessageText message="Explore [other tools](https://datacommons.org)." />,
    );
    const link = screen.getByRole('link', { name: 'other tools' });
    expect(link.getAttribute('href')).toBe('https://datacommons.org');
    expect(link.getAttribute('target')).toBe('_self');
    expect(container.textContent).toBe('Explore other tools.');
  });

  it('renders other Markdown and unsafe links as inline text', () => {
    // Test: Markdown beyond links, an unsafe link, and two paragraphs.
    // Situation: The message holds bold text, a script URL, and a blank line.
    // Expectation: No `strong`, link, or paragraph element renders; the text
    //   content remains.
    const { container } = render(
      <MessageText
        message={'Paused **now**.\n\n[Retry](javascript:alert(1))'}
      />,
    );
    expect(container.querySelector('strong, a, p')).toBeNull();
    expect(container.textContent?.replace(/\s+/g, ' ')).toBe(
      'Paused now. Retry',
    );
  });
});
