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
import { assignCitationNumbers } from "./use_sse_chat";
import type { ChatTurn, ProvenanceItem } from "./use_sse_chat";

const WDI: ProvenanceItem = {
  name: "World Development Indicators",
  url: "https://worldbank.org/wdi",
};
const GHO: ProvenanceItem = { name: "GHO", url: "https://who.int/gho" };
const OECD: ProvenanceItem = { name: "OECD", url: "https://oecd.org/health" };

function turn(provenance: ProvenanceItem[]): ChatTurn {
  return {
    userMessage: "q",
    status: "done",
    toolCalls: [],
    thoughts: [],
    text: "a",
    provenance,
  };
}

describe("assignCitationNumbers", () => {
  it("numbers the first answer from one", () => {
    // Test: The base case.
    // Situation: A single answer citing two sources.
    // Expectation: [1] and [2], as before.
    expect(assignCitationNumbers([turn([WDI, GHO])])).toEqual([[1, 2]]);
  });

  it("keeps counting into the next answer", () => {
    // Test: The reported bug.
    // Situation: A second answer citing a source the first did not.
    // Expectation: It takes the next free number rather than restarting at
    //   [1], which had one numeral naming several unrelated sources.
    expect(assignCitationNumbers([turn([WDI, GHO]), turn([OECD])])).toEqual([
      [1, 2],
      [3],
    ]);
  });

  it("gives a source cited twice the number it already had", () => {
    // Test: A repeat citation.
    // Situation: The second answer cites a source the first already did.
    // Expectation: The original number -- following [1] in the third answer
    //   and [1] in the first has to land on the same dataset.
    expect(assignCitationNumbers([turn([WDI]), turn([WDI, OECD])])).toEqual([
      [1],
      [1, 2],
    ]);
  });

  it("matches on the url, not the display name", () => {
    // Test: Identity of a source across answers.
    // Situation: Two facets of one dataset carry different names.
    // Expectation: One number -- the URL is what says they are the same
    //   source.
    const renamed = { name: "WDI (2024 revision)", url: WDI.url };
    expect(assignCitationNumbers([turn([WDI]), turn([renamed])])).toEqual([
      [1],
      [1],
    ]);
  });

  it("survives a turn rehydrated without provenance", () => {
    // Test: A turn restored from storage by an older build.
    // Situation: chat_session_context JSON.parses persisted turns and filters
    //   them by status alone, so a turn can reach here without the array its
    //   type promises.
    // Expectation: An empty row, not a TypeError that blanks the chat
    //   surface.
    const legacy = {
      ...turn([]),
      provenance: undefined,
    } as unknown as ChatTurn;
    expect(assignCitationNumbers([legacy, turn([WDI])])).toEqual([[], [1]]);
  });

  it("copes with an answer that cited nothing", () => {
    // Test: Empty inputs.
    // Situation: An answer with no provenance, and an empty thread.
    // Expectation: An empty row, and no numbers consumed by it.
    expect(assignCitationNumbers([turn([]), turn([WDI])])).toEqual([[], [1]]);
    expect(assignCitationNumbers([])).toEqual([]);
  });
});
