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
import { citationLead, citationUrlLabel } from "./list_citations";
import type { ProvenanceItem } from "../hooks/use_sse_chat";

describe("citationUrlLabel", () => {
  it("drops the scheme and any trailing slash", () => {
    // Test: The link text of a citation row.
    // Situation: A full URL with a scheme and a trailing slash.
    // Expectation: Neither is shown -- the row reads as a reference, not as a
    //   pasted address.
    expect(
      citationUrlLabel(
        "https://datatopics.worldbank.org/world-development-indicators/",
      ),
    ).toBe("datatopics.worldbank.org/world-development-indicators");
  });

  it("leaves a bare host alone", () => {
    // Test: A URL with nothing to strip.
    // Situation: The data plane reported only a host.
    // Expectation: Unchanged.
    expect(citationUrlLabel("worldbank.org")).toBe("worldbank.org");
  });
});

describe("citationLead", () => {
  const FULL: ProvenanceItem = {
    name: "World Development Indicators",
    url: "https://datatopics.worldbank.org/world-development-indicators",
    provider: "World Bank",
    dataset: "World Development Indicators",
    dateRange: "1960 – 2023",
  };

  it("names the provider, the dataset and the years", () => {
    // Test: The requested citation format.
    // Situation: The data plane reported every field.
    // Expectation: Publisher, dataset and range, in that order.
    expect(citationLead(FULL)).toBe(
      "World Bank, World Development Indicators (1960 – 2023)",
    );
  });

  it("falls back to the display name when the dataset is unnamed", () => {
    // Test: A source described only by name.
    // Situation: No provider, dataset or range.
    // Expectation: The name alone, rather than an empty lead.
    expect(citationLead({ name: "GHO", url: "https://who.int" })).toBe("GHO");
  });

  it("drops the range when the source did not report one", () => {
    // Test: A missing field.
    // Situation: Provider and dataset but no dates.
    // Expectation: No empty parentheses.
    const { dateRange: _dropped, ...noRange } = FULL;
    expect(citationLead(noRange)).toBe(
      "World Bank, World Development Indicators",
    );
  });

  it("does not say the same thing twice", () => {
    // Test: Duplicate provider and dataset.
    // Situation: Some imports report one string in both fields.
    // Expectation: Said once -- "OECD, OECD" reads as a rendering bug rather
    //   than an attribution.
    expect(
      citationLead({
        name: "OECD",
        url: "https://oecd.org",
        provider: "OECD",
        dataset: "OECD",
      }),
    ).toBe("OECD");
  });
});
