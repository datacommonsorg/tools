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
 * @fileoverview Tests for the Toast snackbar's dismissal timing.
 */

import { readFileSync } from 'node:fs';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EXIT_MS, Toast, VISIBLE_MS } from './toast';

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
});
