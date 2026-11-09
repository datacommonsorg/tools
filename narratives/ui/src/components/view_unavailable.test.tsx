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

import { cleanup, render, screen } from '@testing-library/react';
import { useReducedMotion } from 'motion/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UnavailableView } from '@/src/components/view_unavailable';
import { resetInstanceConfigForTests } from '@/src/config/instance_config';
import {
  DEFAULT_UNAVAILABLE_MESSAGE,
  resetRuntimeConfigForTests,
} from '@/src/config/runtime_config';

vi.mock('motion/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: vi.fn(),
}));

const writeSlot = (id: string, payload: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = id;
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(payload);
  document.head.appendChild(slot);
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
  it('renders the headline, tagline, and configured message in a status region', () => {
    // Test: Chat disabled with a custom message and custom branding.
    // Situation: #instance-config sets a headline and tagline, and
    //   #runtime-config disables chat with a custom message.
    // Expectation: The heading and tagline render, and the message renders
    //   inside the `status` region.
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
    expect(screen.getByRole('status').textContent).toBe(
      'Chat is paused for maintenance.',
    );
  });

  it('renders the default message when none is configured', () => {
    // Test: Chat disabled without a message.
    // Situation: #runtime-config holds only `enable_chat: false`.
    // Expectation: The status region holds the default unavailable message.
    writeSlot('runtime-config', { enable_chat: false });
    render(<UnavailableView />);
    expect(screen.getByRole('status').textContent).toBe(
      DEFAULT_UNAVAILABLE_MESSAGE,
    );
  });

  it('omits the tagline paragraph when the tagline is empty', () => {
    // Test: Instance configured without a tagline.
    // Situation: #instance-config sets `tagline` to an empty string.
    // Expectation: Only the message paragraph renders below the heading.
    writeSlot('instance-config', { tagline: '' });
    const { container } = render(<UnavailableView />);
    expect(container.querySelectorAll('p')).toHaveLength(1);
    expect(container.querySelector('p')?.textContent).toBe(
      DEFAULT_UNAVAILABLE_MESSAGE,
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
    expect(screen.getByRole('status').textContent).toBe(
      DEFAULT_UNAVAILABLE_MESSAGE,
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
    expect(screen.getByRole('status').textContent).toBe(
      DEFAULT_UNAVAILABLE_MESSAGE,
    );
  });
});
