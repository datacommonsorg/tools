/*
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

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PromptInput } from './input_prompt';

afterEach(cleanup);

describe('PromptInput', () => {
  it('submits on Enter but not on Shift+Enter', () => {
    // Test: Keyboard submit.
    // Situation: The user presses Enter, then Shift+Enter, in the textarea.
    // Expectation: Only the bare Enter submits; Shift+Enter is a newline.
    const onSubmit = vi.fn();
    render(
      <PromptInput
        value="gdp"
        placeholder="Ask"
        onValueChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    const textbox = screen.getByRole('textbox');
    fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.keyDown(textbox, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('does not submit on Enter while an IME composition is open', () => {
    // Test: IME composition.
    // Situation: The user presses Enter to commit a Japanese/Chinese candidate.
    // Expectation: The Enter commits the composition; nothing is submitted.
    const onSubmit = vi.fn();
    render(
      <PromptInput
        value="gdp"
        placeholder="Ask"
        onValueChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.keyDown(screen.getByRole('textbox'), {
      key: 'Enter',
      isComposing: true,
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits from the button only when there is text', () => {
    // Test: Button submit.
    // Situation: The box holds only whitespace, then real text.
    // Expectation: The button is disabled for whitespace; with text, clicking
    // it submits through the form.
    const onSubmit = vi.fn();
    const props = { placeholder: 'Ask', onValueChange: vi.fn(), onSubmit };
    const view = render(<PromptInput value="   " {...props} />);
    expect(screen.getByRole('button', { name: 'Submit' })).toHaveProperty(
      'disabled',
      true,
    );
    view.rerender(<PromptInput value="gdp" {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('does not submit on Enter when there is no text', () => {
    // Test: Keyboard submit with no text.
    // Situation: The box holds only whitespace and the user presses Enter.
    // Expectation: Nothing is submitted.
    const onSubmit = vi.fn();
    render(
      <PromptInput
        value="   "
        placeholder="Ask"
        onValueChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('turns the button into a stop control while streaming', () => {
    // Test: Streaming state.
    // Situation: A response is streaming and the user presses the button.
    // Expectation: The textarea locks and shows "Thinking..." but keeps its
    // name; the button is named Stop and stops rather than submits.
    const onSubmit = vi.fn();
    const onStop = vi.fn();
    render(
      <PromptInput
        value=""
        placeholder="Ask"
        onValueChange={vi.fn()}
        onSubmit={onSubmit}
        isStreaming
        onStop={onStop}
      />,
    );
    const textbox = screen.getByRole('textbox', { name: 'Ask' });
    expect(textbox).toHaveProperty('disabled', true);
    expect(textbox).toHaveProperty('placeholder', 'Thinking...');
    fireEvent.click(screen.getByRole('button', { name: 'Stop Response' }));
    expect(onStop).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('walks a raised dot across the placeholder while streaming', () => {
    // Test: Streaming placeholder animation.
    // Situation: A response streams for several 400ms ticks.
    // Expectation: A `⋅` steps across the last two dots, then the plain
    // ellipsis returns and the cycle repeats; a stream stopped mid-cycle
    // leaves the next one starting from the plain ellipsis.
    vi.useFakeTimers();
    try {
      const prompt = (isStreaming: boolean) => (
        <PromptInput
          value=""
          placeholder="Ask"
          onValueChange={vi.fn()}
          onSubmit={vi.fn()}
          isStreaming={isStreaming}
        />
      );
      const { rerender } = render(prompt(true));
      const textbox = screen.getByRole('textbox', { name: 'Ask' });
      const frames = [];
      for (let step = 0; step < 4; step++) {
        frames.push(textbox.getAttribute('placeholder'));
        act(() => vi.advanceTimersByTime(400));
      }
      expect(frames).toEqual([
        'Thinking...',
        'Thinking.⋅.',
        'Thinking..⋅',
        'Thinking...',
      ]);
      act(() => vi.advanceTimersByTime(400));
      rerender(prompt(false));
      rerender(prompt(true));
      expect(textbox.getAttribute('placeholder')).toBe('Thinking...');
    } finally {
      vi.useRealTimers();
    }
  });

  it('holds the placeholder on the first frame under reduced motion', () => {
    // Test: Reduced-motion streaming placeholder.
    // Situation: The user prefers reduced motion and a response streams for
    // several 400ms ticks.
    // Expectation: The placeholder stays at the plain "Thinking...".
    vi.useFakeTimers();
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
    }));
    try {
      render(
        <PromptInput
          value=""
          placeholder="Ask"
          onValueChange={vi.fn()}
          onSubmit={vi.fn()}
          isStreaming
        />,
      );
      const textbox = screen.getByRole('textbox', { name: 'Ask' });
      for (let step = 0; step < 4; step++) {
        expect(textbox.getAttribute('placeholder')).toBe('Thinking...');
        act(() => vi.advanceTimersByTime(400));
      }
    } finally {
      vi.unstubAllGlobals();
      vi.useRealTimers();
    }
  });
});
