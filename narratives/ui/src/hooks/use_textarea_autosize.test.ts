/**
 * @fileoverview Tests for the useTextareaAutosize hook.
 */

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useTextareaAutosize } from "./use_textarea_autosize";

const LINE_HEIGHT = 24;

// happy-dom does no layout, so the textarea's scroll metrics are stubbed on
// the prototype: `lines` is how many lines the current text occupies.
let lines = 1;

beforeAll(() => {
  vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockImplementation(
    () => lines * LINE_HEIGHT,
  );
  vi.spyOn(HTMLTextAreaElement.prototype, "clientHeight", "get").mockReturnValue(
    LINE_HEIGHT,
  );
});

afterEach(() => {
  lines = 1;
});

afterAll(() => {
  vi.restoreAllMocks();
});

/** Runs the hook against a fresh textarea, starting with `value`. */
const renderAutosize = (value: string) => {
  const textarea = document.createElement("textarea");
  const ref = { current: textarea };
  const hook = renderHook(
    ({ value }) => useTextareaAutosize(ref, value),
    { initialProps: { value } },
  );
  return { textarea, hook };
};

describe("useTextareaAutosize", () => {
  it("stays collapsed while the text fits on one line", () => {
    // Test: Single-line value.
    // Situation: The text does not wrap.
    // Expectation: Not expanded; the height is one line.
    const { textarea, hook } = renderAutosize("short");
    expect(hook.result.current).toBe(false);
    expect(textarea.style.height).toBe(`${LINE_HEIGHT}px`);
  });

  it("expands and grows to fit text that spans several lines", () => {
    // Test: Multi-line value.
    // Situation: The text wraps to three lines.
    // Expectation: Expanded; the height fits all three lines.
    lines = 3;
    const { textarea, hook } = renderAutosize("a value long enough to wrap");
    expect(hook.result.current).toBe(true);
    expect(textarea.style.height).toBe(`${3 * LINE_HEIGHT}px`);
  });

  it("stays one line when empty even if the placeholder wraps", () => {
    // Test: Empty value on a narrow textarea.
    // Situation: The placeholder wraps, so the textarea reports two lines.
    // Expectation: Not expanded; the height stays one line.
    lines = 2;
    const { textarea, hook } = renderAutosize("");
    expect(hook.result.current).toBe(false);
    expect(textarea.style.height).toBe(`${LINE_HEIGHT}px`);
  });

  it("follows the value as it grows and shrinks", () => {
    // Test: Changing value.
    // Situation: The value goes from one line to two and back to one.
    // Expectation: Expansion and height track each change.
    const { textarea, hook } = renderAutosize("short");

    lines = 2;
    hook.rerender({ value: "a value long enough to wrap" });
    expect(hook.result.current).toBe(true);
    expect(textarea.style.height).toBe(`${2 * LINE_HEIGHT}px`);

    lines = 1;
    hook.rerender({ value: "short" });
    expect(hook.result.current).toBe(false);
    expect(textarea.style.height).toBe(`${LINE_HEIGHT}px`);
  });

  it("does nothing when the ref is not attached", () => {
    // Test: Unattached ref.
    // Situation: The textarea has not mounted, so the ref is null.
    // Expectation: Not expanded and no error.
    const ref = { current: null };
    const { result } = renderHook(() => useTextareaAutosize(ref, "text"));
    expect(result.current).toBe(false);
  });
});
