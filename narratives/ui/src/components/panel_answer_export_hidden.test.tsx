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
 * @fileoverview Tests the answer panel with the shipped PDF export setting.
 * Kept apart from `panel_answer.test.tsx`, which mocks the export on.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { AnswerPanel } from '@/src/components/panel_answer';

afterEach(cleanup);

it('hides the Export PDF controls on a finished answer', () => {
  // Test: The shipped PDF export setting.
  // Situation: A finished text-only answer mounts after the stream closed,
  //   which shows the export controls when export is enabled.
  // Expectation: No Export PDF control renders.
  render(
    <AnswerPanel
      turn={{
        userMessage: 'What is the population of France?',
        status: 'done',
        toolCalls: [],
        thoughts: [],
        text: 'France has about 68 million.',
        blocks: [
          { index: 0, type: 'text', markdown: 'France has about 68 million.' },
        ],
        provenance: [],
      }}
      isStreaming={false}
    />,
  );

  expect(screen.queryByText('France has about 68 million.')).not.toBeNull();
  expect(screen.queryAllByRole('button', { name: 'Export PDF' })).toHaveLength(
    0,
  );
});
