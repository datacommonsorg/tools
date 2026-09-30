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

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DISCLAIMER_TEXT, DisclaimerNote } from "./note_disclaimer";

afterEach(cleanup);

describe("DisclaimerNote", () => {
  it("draws the rule before the note, not after it", () => {
    // Test: Position of the divider within the disclaimer section.
    // Situation: The note renders with its default text.
    // Expectation: The <hr> is the section's first child, so it reads as the
    //   end of the answer rather than as the end of the disclaimer.
    const { container } = render(<DisclaimerNote />);
    const section = container.querySelector("section");
    expect(section?.firstElementChild?.tagName).toBe("HR");
    expect(section?.lastElementChild?.tagName).not.toBe("HR");
  });

  it("still shows the approved wording", () => {
    // Test: The disclaimer text survives the reorder.
    // Situation: The note renders with its default text.
    // Expectation: The approved AI-content wording is present.
    const { container } = render(<DisclaimerNote />);
    expect(container.textContent).toContain(DISCLAIMER_TEXT);
  });
});
