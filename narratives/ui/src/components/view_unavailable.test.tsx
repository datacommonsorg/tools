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
 * @fileoverview Tests for UnavailableView.
 */

import { cleanup, render, screen, within } from '@testing-library/react';
import { useReducedMotion } from 'motion/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UnavailableView } from '@/src/components/view_unavailable';
import { resetInstanceConfigForTests } from '@/src/config/instance_config';
import {
  DEFAULT_UNAVAILABLE_TITLE,
  resetRuntimeConfigForTests,
} from '@/src/config/runtime_config';

/** Visible text of the default unavailable message, Markdown removed. */
const DEFAULT_MESSAGE_TEXT =
  'Due to high traffic, this feature is temporarily paused. Capacity is ' +
  'being scaled to restore service as quickly as possible. Please try again ' +
  'later, or explore other tools in Data Commons.';

vi.mock('motion/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: vi.fn(),
}));

/**
 * Replaces the `<script>` element `id` with one holding `payload`, and clears
 * both cached configurations so the next read sees it.
 */
const writeSlot = (id: string, payload: Record<string, unknown>): void => {
  document.getElementById(id)?.remove();
  const slot = document.createElement('script');
  slot.id = id;
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(payload);
  document.head.appendChild(slot);
  resetInstanceConfigForTests();
  resetRuntimeConfigForTests();
};

beforeEach(() => {
  vi.mocked(useReducedMotion).mockReturnValue(true);
});

afterEach(() => {
  cleanup();
  document.getElementById('instance-config')?.remove();
  document.getElementById('runtime-config')?.remove();
  resetInstanceConfigForTests();
  resetRuntimeConfigForTests();
  vi.restoreAllMocks();
});

describe('UnavailableView', () => {
  it('renders the headline, tagline, and configured message in a note', () => {
    // Test: Chat disabled with a custom message and custom branding.
    // Situation: #instance-config sets a headline and tagline, and
    //   #runtime-config disables chat with a custom message.
    // Expectation: The heading and tagline render, and the message renders
    //   inside the `note`.
    writeSlot('instance-config', {
      headline: 'Acme explorer',
      tagline: 'powered by Acme',
    });
    writeSlot('runtime-config', {
      enable_chat: false,
      unavailable_message: 'Chat is paused for maintenance.',
    });
    render(<UnavailableView />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Acme explorer',
    );
    expect(screen.getByText('powered by Acme')).toBeTruthy();
    expect(
      within(screen.getByRole('note')).getByText(
        'Chat is paused for maintenance.',
      ),
    ).toBeTruthy();
  });

  it('names the note with its default title heading when none is configured', () => {
    // Test: Default title of the unavailable note.
    // Situation: The view renders with the default configuration.
    // Expectation: The note is named by a level-2 heading holding the default
    //   title.
    render(<UnavailableView />);
    expect(
      screen.getByRole('note', { name: DEFAULT_UNAVAILABLE_TITLE }),
    ).toBeTruthy();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(
      DEFAULT_UNAVAILABLE_TITLE,
    );
  });

  it('names the note with a configured title heading', () => {
    // Test: Custom title of the unavailable note.
    // Situation: #runtime-config disables chat with a custom unavailable title.
    // Expectation: The note is named by a level-2 heading holding the
    //   configured title.
    writeSlot('runtime-config', {
      enable_chat: false,
      unavailable_title: 'Scheduled maintenance',
    });
    render(<UnavailableView />);
    expect(
      screen.getByRole('note', { name: 'Scheduled maintenance' }),
    ).toBeTruthy();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(
      'Scheduled maintenance',
    );
  });

  it('renders the default message when none is configured', () => {
    // Test: Chat disabled without a message.
    // Situation: #runtime-config holds only `enable_chat: false`.
    // Expectation: The note holds the default message, whose Markdown link
    //   renders as a same-tab link to Data Commons.
    writeSlot('runtime-config', { enable_chat: false });
    render(<UnavailableView />);
    const note = screen.getByRole('note');
    expect(note.querySelector('p')?.textContent).toBe(DEFAULT_MESSAGE_TEXT);
    const link = within(note).getByRole('link', {
      name: 'tools in Data Commons',
    });
    expect(link.getAttribute('href')).toBe('https://datacommons.org');
    expect(link.getAttribute('target')).toBe('_self');
  });

  it('omits the tagline paragraph when the tagline is empty', () => {
    // Test: Instance configured without a tagline.
    // Situation: #instance-config sets `tagline` to an empty string.
    // Expectation: No paragraph renders with the heading; the message
    //   paragraph renders only inside the note, which is portaled to <body>.
    writeSlot('instance-config', { tagline: '' });
    const { container } = render(<UnavailableView />);
    expect(container.querySelector('p')).toBeNull();
    expect(screen.getByRole('note').querySelector('p')?.textContent).toBe(
      DEFAULT_MESSAGE_TEXT,
    );
  });

  it('renders no prompt box or suggestion chips', () => {
    // Test: Controls on the unavailable view.
    // Situation: The view renders with the built-in suggestions configured.
    // Expectation: No textbox and no button render.
    render(<UnavailableView />);
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders at rest when the user prefers reduced motion', () => {
    // Test: Reduced-motion preference on.
    // Situation: `useReducedMotion` reports `true`.
    // Expectation: The heading and the message render with no hidden intro
    //   state on the heading.
    vi.mocked(useReducedMotion).mockReturnValue(true);
    render(<UnavailableView />);
    expect(screen.getByRole('heading', { level: 1 }).style.opacity).toBe('');
    expect(screen.getByRole('note').querySelector('p')?.textContent).toBe(
      DEFAULT_MESSAGE_TEXT,
    );
  });

  it('starts the intro from the hidden state when motion is allowed', () => {
    // Test: Reduced-motion preference off.
    // Situation: `useReducedMotion` reports `false`.
    // Expectation: The heading starts transparent for the fade-up, and the
    //   message is rendered.
    vi.mocked(useReducedMotion).mockReturnValue(false);
    render(<UnavailableView />);
    expect(screen.getByRole('heading', { level: 1 }).style.opacity).toBe('0');
    expect(screen.getByRole('note').querySelector('p')?.textContent).toBe(
      DEFAULT_MESSAGE_TEXT,
    );
  });
});
