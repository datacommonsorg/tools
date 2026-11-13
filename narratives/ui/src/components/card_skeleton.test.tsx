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
 * @fileoverview Tests for the loading skeleton card.
 */

import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { SkeletonCard } from '@/src/components/card_skeleton';

afterEach(() => {
  cleanup();
});

describe('SkeletonCard', () => {
  it('shows a ghost line instead of text in its header', () => {
    // Test: Header of the loading card.
    // Situation: The skeleton renders while an answer is on its way.
    // Expectation: The header holds no text, so it neither repeats the
    //   question nor competes with the reasoning status, and shows one
    //   pulsing ghost line hidden from assistive technology.
    const { container } = render(<SkeletonCard />);
    const header = container.querySelector('.print-question');

    expect(header?.textContent).toBe('');
    const ghost = header?.querySelector('[aria-hidden="true"]');
    expect(ghost?.className).toContain('animate-pulse');
  });
});
