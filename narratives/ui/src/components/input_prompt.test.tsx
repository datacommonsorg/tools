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

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PromptInput } from "./input_prompt";

afterEach(cleanup);

describe("PromptInput", () => {
  it("submits on Enter but not on Shift+Enter", () => {
    // Test: Keyboard submit.
    // Situation: The user presses Enter, then Shift+Enter, in the textarea.
    // Expectation: Only the bare Enter submits; Shift+Enter is a newline.
    const onSubmit = vi.fn();
    render(
      <PromptInput value="gdp" placeholder="Ask" onValueChange={() => {}} onSubmit={onSubmit} />,
    );
    const textbox = screen.getByRole("textbox");
    fireEvent.keyDown(textbox, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("does not submit on Enter while an IME composition is open", () => {
    // Test: IME composition.
    // Situation: The user presses Enter to commit a Japanese/Chinese candidate.
    // Expectation: The Enter commits the composition; nothing is submitted.
    const onSubmit = vi.fn();
    render(
      <PromptInput value="gdp" placeholder="Ask" onValueChange={() => {}} onSubmit={onSubmit} />,
    );
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", isComposing: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits from the button only when there is text", () => {
    // Test: Button submit.
    // Situation: The box holds only whitespace, then real text.
    // Expectation: The button is disabled for whitespace; with text, clicking
    // it submits through the form.
    const onSubmit = vi.fn();
    const props = { placeholder: "Ask", onValueChange: () => {}, onSubmit };
    const view = render(<PromptInput value="   " {...props} />);
    expect(screen.getByRole("button", { name: "Submit" })).toHaveProperty("disabled", true);
    view.rerender(<PromptInput value="gdp" {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("turns the button into a stop control while streaming", () => {
    // Test: Streaming state.
    // Situation: A response is streaming and the user presses the button.
    // Expectation: The textarea locks, the button is named Stop and stops
    // rather than submits.
    const onSubmit = vi.fn();
    const onStop = vi.fn();
    render(
      <PromptInput
        value=""
        placeholder="Ask"
        onValueChange={() => {}}
        onSubmit={onSubmit}
        isStreaming
        onStop={onStop}
      />,
    );
    expect(screen.getByRole("textbox")).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Stop Response" }));
    expect(onStop).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
