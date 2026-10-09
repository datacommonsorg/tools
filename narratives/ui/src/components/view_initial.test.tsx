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

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { InitialView } from "./view_initial";

const LINE_HEIGHT = 24;

// happy-dom does no layout, so the textarea's scroll metrics are stubbed on
// the prototype: `lines` is how many lines the current text occupies.
let lines = 1;

beforeAll(() => {
  // Motion reads the reduced-motion preference once per module and caches it,
  // so the whole file runs with reduced motion on.
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockImplementation(
    () => lines * LINE_HEIGHT,
  );
  vi.spyOn(HTMLTextAreaElement.prototype, "clientHeight", "get").mockReturnValue(
    LINE_HEIGHT,
  );
});

afterEach(() => {
  cleanup();
  lines = 1;
});

afterAll(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Renders the view with `query` and returns the search box element. */
const renderSearchBox = (query: string) => {
  const view = render(
    <InitialView
      query={query}
      setQuery={() => {}}
      onSend={() => {}}
    />,
  );
  const searchBox = screen.getByRole("textbox").closest("form")!;
  return { view, searchBox };
};

describe("InitialView search box", () => {
  it("stays a pill while the text fits on one line", () => {
    // Test: Single-line query.
    // Situation: The text does not wrap inside the pill.
    // Expectation: The box keeps its fully rounded pill shape.
    const { searchBox } = renderSearchBox("population of France");
    expect(searchBox.className).toContain("rounded-pill");
    expect(searchBox.className).not.toContain("rounded-input");
  });

  it("expands once the text wraps past one line", () => {
    // Test: Wrapped query.
    // Situation: The text is wider than the pill and wraps to a second line.
    // Expectation: The box switches to the expanded input radius.
    lines = 2;
    const { searchBox } = renderSearchBox("a question long enough to wrap");
    expect(searchBox.className).toContain("rounded-input");
  });

  it("stays a pill when empty even if the placeholder wraps", () => {
    // Test: Empty query on a narrow viewport.
    // Situation: The placeholder wraps, so the textarea reports two lines.
    // Expectation: The box keeps its pill shape; only typed text expands it.
    lines = 2;
    const { searchBox } = renderSearchBox("");
    expect(searchBox.className).toContain("rounded-pill");
    expect(searchBox.className).not.toContain("rounded-input");
  });

  it("collapses back to a pill when the text fits again", () => {
    // Test: Shrinking query.
    // Situation: An expanded box has its text shortened to a single line.
    // Expectation: The box returns to the pill shape.
    lines = 2;
    const { view, searchBox } = renderSearchBox("a question long enough");
    lines = 1;
    view.rerender(
      <InitialView
        query="short"
        setQuery={() => {}}
        onSend={() => {}}
        />,
    );
    expect(searchBox.className).toContain("rounded-pill");
  });
});

describe("InitialView intro", () => {
  it("renders at rest when the user prefers reduced motion", () => {
    // Test: Reduced-motion preference.
    // Situation: The OS reports prefers-reduced-motion.
    // Expectation: The heading renders visible, not at the hidden intro state.
    renderSearchBox("");
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.style.opacity).not.toBe("0");
    expect(heading.style.transform).toBe("");
  });
});
