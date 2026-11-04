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
 * @fileoverview Tests for FollowUpQuestions rendering and click handling.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FollowUpQuestions } from './questions_follow_up';

afterEach(cleanup);

describe('FollowUpQuestions', () => {
  it('renders nothing for an empty list', () => {
    // Test: Rendering with no follow-up questions.
    // Situation: The agent returned an empty list.
    // Expectation: The component renders no markup at all.
    const { container } = render(<FollowUpQuestions questions={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('asks the question that was clicked', () => {
    // Test: Clicking a follow-up question.
    // Situation: Two questions render and the user clicks the second.
    // Expectation: onAsk is called once, with the clicked question's text.
    const onAsk = vi.fn();
    render(
      <FollowUpQuestions
        questions={['What about Germany?', 'How has it changed since 2000?']}
        onAsk={onAsk}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'How has it changed since 2000?' }),
    );

    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledWith('How has it changed since 2000?');
  });
});
