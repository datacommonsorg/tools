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

import { describe, expect, it } from "vitest";
import {
  citationAnchorId,
  displayCitationNumber,
  isCitable,
  sourceLabel,
} from "./chip_citation";
import type { ProvenanceItem } from "../hooks/use_sse_chat";

const SOURCES: ProvenanceItem[] = [
  { name: "World Development Indicators", url: "https://worldbank.org/wdi" },
  { name: "", url: "https://oecd.org/wage-gap" },
  { name: "OECD", url: "https://oecd.org" },
];

describe("sourceLabel", () => {
  it("names the source a chip points at", () => {
    expect(sourceLabel(1, SOURCES)).toBe("World Development Indicators");
    expect(sourceLabel(3, SOURCES)).toBe("OECD");
  });

  it("is 1-based, matching the order the Citations list renders", () => {
    // [1] is sources[0]. Off-by-one here would label every chip with its
    // neighbor's source, which reads as correct and is not.
    expect(sourceLabel(2, SOURCES)).not.toBe("World Development Indicators");
  });

  it("falls back to the URL when the source has no name", () => {
    expect(sourceLabel(2, SOURCES)).toBe("https://oecd.org/wage-gap");
  });

  it("does not repeat itself when there is no source to name", () => {
    // sourceLabel already yields "Source n" past the end, so the aria-label
    // must not prefix it again ("Source 9: Source 9").
    expect(sourceLabel(9, SOURCES)).toBe("Source 9");
  });

  it("falls back to the bare number past the end of the list", () => {
    // The agent sometimes emits a marker before provenance has caught up.
    expect(sourceLabel(4, SOURCES)).toBe("Source 4");
    expect(sourceLabel(1, [])).toBe("Source 1");
    expect(sourceLabel(1, undefined)).toBe("Source 1");
  });
});

describe("isCitable", () => {
  it("accepts every number the Citations list actually renders", () => {
    // The whole numbering contract: [n] is row n, never rewritten, so every
    // in-range marker links and no in-range source is skipped.
    expect(isCitable(1, SOURCES)).toBe(true);
    expect(isCitable(2, SOURCES)).toBe(true);
    expect(isCitable(3, SOURCES)).toBe(true);
  });

  it("rejects a number past the end of the list", () => {
    // No #source-4 anchor is emitted, so linking it produced a dead click.
    expect(isCitable(4, SOURCES)).toBe(false);
    expect(isCitable(99, SOURCES)).toBe(false);
  });

  it("rejects a non-positive number", () => {
    expect(isCitable(0, SOURCES)).toBe(false);
    expect(isCitable(-1, SOURCES)).toBe(false);
  });

  it("rejects everything when there is no provenance at all", () => {
    expect(isCitable(1, [])).toBe(false);
    expect(isCitable(1, undefined)).toBe(false);
  });
});

describe("displayCitationNumber", () => {
  it("relabels a position with the number the thread gave it", () => {
    // Test: The mapping from the agent's numbering to the reader's.
    // Situation: This answer's two sources were labelled [3] and [4].
    // Expectation: Position 1 shows as 3 and position 2 as 4.
    expect(displayCitationNumber(1, [3, 4])).toBe(3);
    expect(displayCitationNumber(2, [3, 4])).toBe(4);
  });

  it("is the position itself when nothing relabelled it", () => {
    // Test: The fallback.
    // Situation: No mapping was supplied.
    // Expectation: The position, so a panel on its own still numbers itself.
    expect(displayCitationNumber(2)).toBe(2);
    expect(displayCitationNumber(2, [])).toBe(2);
  });
});

describe("citationAnchorId", () => {
  it("scopes the anchor to its turn", () => {
    // Test: Anchor uniqueness.
    // Situation: Two answers cite one source, so they share its label.
    // Expectation: Different ids -- sharing one is how a chip in the third
    //   answer used to scroll to a row under the first.
    expect(citationAnchorId(0, 1)).not.toBe(citationAnchorId(2, 1));
  });

  it("is stable for one turn and number", () => {
    // Test: Determinism.
    // Situation: The same turn and label, asked twice.
    // Expectation: The same id, so the chip and the row agree.
    expect(citationAnchorId(2, 4)).toBe(citationAnchorId(2, 4));
  });
});
