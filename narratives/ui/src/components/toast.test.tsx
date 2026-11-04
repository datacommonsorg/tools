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
 * @fileoverview Tests for the Toast snackbar's dismissal timing, pausing, close
 * button, and focus return.
 */

import { readFileSync } from 'node:fs';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EXIT_MS, RESUME_MS, Toast, VISIBLE_MS } from '@/src/components/toast';

// Motion caches the media query after its first read, so stub the hook rather
// than matchMedia to flip reduced motion per test.
const motion = vi.hoisted(() => ({ reduce: false }));
vi.mock('motion/react', () => ({ useReducedMotion: () => motion.reduce }));

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    motion.reduce = false;
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('keeps EXIT_MS equal to the --animate-exit duration', () => {
    // Test: The unmount delay against the exit animation.
    // Situation: EXIT_MS delays onDismiss; --animate-exit in index.css plays
    //            the slide-out.
    // Expectation: Both durations are equal, so the toast is neither cut off
    //              mid-animation nor left invisible but mounted.
    // Vitest runs from the ui/ package root.
    const css = readFileSync('src/index.css', 'utf8');
    const duration = css.match(/--animate-exit:\s*exit\s+(\d+)ms/);
    expect(duration).not.toBeNull();
    expect(Number(duration?.[1])).toBe(EXIT_MS);
  });

  it('plays the exit animation before dismissing', () => {
    // Test: Self-dismissal with motion allowed.
    // Situation: The toast has been visible for VISIBLE_MS.
    // Expectation: It switches to the exit animation and calls onDismiss only
    //              once EXIT_MS has passed.
    const onDismiss = vi.fn();
    render(<Toast message="PDF downloaded" onDismiss={onDismiss} />);
    const toast = screen.getByRole('status');
    expect(toast.className).toContain('motion-safe:animate-enter');

    act(() => vi.advanceTimersByTime(VISIBLE_MS));
    expect(toast.className).toContain('motion-safe:animate-exit');
    expect(onDismiss).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(EXIT_MS));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('dismisses without waiting for the exit under reduced motion', () => {
    // Test: Self-dismissal with reduced motion.
    // Situation: The user prefers reduced motion, so no exit animation plays.
    // Expectation: onDismiss fires as soon as VISIBLE_MS has passed.
    motion.reduce = true;
    const onDismiss = vi.fn();
    render(<Toast message="PDF downloaded" onDismiss={onDismiss} />);

    act(() => vi.advanceTimersByTime(VISIBLE_MS));
    act(() => vi.advanceTimersByTime(0));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('plays the exit animation when the close button is pressed', () => {
    // Test: Manual dismissal.
    // Situation: The user presses Close before VISIBLE_MS has passed.
    // Expectation: The toast exits right away and onDismiss fires after
    //              EXIT_MS, without waiting for the auto-dismiss timer.
    const onDismiss = vi.fn();
    render(<Toast message="PDF downloaded" onDismiss={onDismiss} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('status').className).toContain(
      'motion-safe:animate-exit',
    );

    act(() => vi.advanceTimersByTime(EXIT_MS));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('pauses the countdown while hovered', () => {
    // Test: Hover pause.
    // Situation: The pointer rests on the toast past VISIBLE_MS, then leaves.
    // Expectation: The toast stays up while hovered and leaves RESUME_MS
    //              after the pointer does.
    render(<Toast message="PDF downloaded" onDismiss={vi.fn()} />);
    const toast = screen.getByRole('status');

    fireEvent.pointerEnter(toast);
    act(() => vi.advanceTimersByTime(VISIBLE_MS * 2));
    expect(toast.className).toContain('motion-safe:animate-enter');

    fireEvent.pointerLeave(toast);
    act(() => vi.advanceTimersByTime(RESUME_MS - 1));
    expect(toast.className).toContain('motion-safe:animate-enter');
    act(() => vi.advanceTimersByTime(1));
    expect(toast.className).toContain('motion-safe:animate-exit');
  });

  it('holds while focused and returns focus when closed', () => {
    // Test: Keyboard dismissal.
    // Situation: A keyboard user focuses Close, waits past VISIBLE_MS, then
    //            presses it.
    // Expectation: The toast does not time out under focus, and on close the
    //              focus moves to returnFocusRef instead of falling to <body>.
    const prompt = document.createElement('textarea');
    document.body.append(prompt);
    const onDismiss = vi.fn();
    render(
      <Toast
        message="PDF downloaded"
        onDismiss={onDismiss}
        returnFocusRef={{ current: prompt }}
      />,
    );
    const close = screen.getByRole('button', { name: 'Close' });

    act(() => close.focus());
    act(() => vi.advanceTimersByTime(VISIBLE_MS * 2));
    expect(onDismiss).not.toHaveBeenCalled();

    fireEvent.click(close);
    act(() => vi.advanceTimersByTime(EXIT_MS));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(prompt);
    prompt.remove();
  });

  it('moves focus to returnFocusRef when it times out', () => {
    // Test: Focus after self-dismissal.
    // Situation: The toast runs its full VISIBLE_MS untouched.
    // Expectation: Once it unmounts, focus is on returnFocusRef.
    const prompt = document.createElement('textarea');
    document.body.append(prompt);
    render(
      <Toast
        message="PDF downloaded"
        onDismiss={vi.fn()}
        returnFocusRef={{ current: prompt }}
      />,
    );

    act(() => vi.advanceTimersByTime(VISIBLE_MS));
    act(() => vi.advanceTimersByTime(EXIT_MS));
    expect(document.activeElement).toBe(prompt);
    prompt.remove();
  });

  it('leaves focus alone on touch devices', () => {
    // Test: Focus after dismissal on a touch-first device.
    // Situation: The primary pointer is coarse, and the toast times out.
    // Expectation: returnFocusRef is not focused, so no on-screen keyboard
    //              opens unasked.
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query === '(pointer: coarse)',
      media: query,
    }));
    const prompt = document.createElement('textarea');
    document.body.append(prompt);
    render(
      <Toast
        message="PDF downloaded"
        onDismiss={vi.fn()}
        returnFocusRef={{ current: prompt }}
      />,
    );

    act(() => vi.advanceTimersByTime(VISIBLE_MS));
    act(() => vi.advanceTimersByTime(EXIT_MS));
    expect(document.activeElement).not.toBe(prompt);
    prompt.remove();
  });

  it('leaves focus where the user moved it', () => {
    // Test: Focus after self-dismissal once the user has moved on.
    // Situation: After the toast appears, the user opens a dialog that takes
    //            focus, and the toast then times out.
    // Expectation: Focus stays in the dialog instead of jumping to
    //              returnFocusRef behind it.
    const prompt = document.createElement('textarea');
    const dialogClose = document.createElement('button');
    document.body.append(prompt, dialogClose);
    render(
      <Toast
        message="PDF downloaded"
        onDismiss={vi.fn()}
        returnFocusRef={{ current: prompt }}
      />,
    );

    act(() => dialogClose.focus());
    act(() => vi.advanceTimersByTime(VISIBLE_MS));
    act(() => vi.advanceTimersByTime(EXIT_MS));
    expect(document.activeElement).toBe(dialogClose);
    prompt.remove();
    dialogClose.remove();
  });
});
