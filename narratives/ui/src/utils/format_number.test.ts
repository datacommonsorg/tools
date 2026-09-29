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
  formatNumericToken,
  isNeutralText,
  isNumericText,
  isYearText,
  splitFormattedNumbers,
} from "./format_number";

/** The display string, or the token itself when nothing was changed. */
function shown(raw: string): string {
  return formatNumericToken(raw)?.display ?? raw;
}

describe("formatNumericToken", () => {
  it("caps a long decimal at two places", () => {
    // Test: Rounding of a full-precision value.
    // Situation: The data plane returns life expectancy to eleven decimals.
    // Expectation: The display form keeps two.
    expect(shown("84.0412195122")).toBe("84.04");
    expect(shown("82.8426829268")).toBe("82.84");
    expect(shown("83.793902439")).toBe("83.79");
  });

  it("caps rather than pads", () => {
    // Test: A value already short enough.
    // Situation: The token carries two decimals, one decimal, or none.
    // Expectation: Nothing is rewritten -- padding 84.5 to 84.50 would claim a
    //   precision the answer never stated.
    expect(formatNumericToken("84.56")).toBeNull();
    expect(formatNumericToken("84.5")).toBeNull();
    expect(formatNumericToken("12")).toBeNull();
  });

  it("leaves years alone", () => {
    // Test: The number most likely to sit in a table of figures.
    // Situation: The token is a bare four-digit year.
    // Expectation: Nothing is rewritten -- both "2,023" and a compacted form
    //   would be wrong.
    expect(formatNumericToken("2023")).toBeNull();
    expect(formatNumericToken("1960")).toBeNull();
  });

  it("compacts millions and up", () => {
    // Test: Magnitudes a reader cannot count zeros on.
    // Situation: Tokens at 1e6, 1e9 and 1e12.
    // Expectation: The scaled value carries an M, B or T suffix.
    expect(shown("1234567")).toBe("1.23M");
    expect(shown("1000000")).toBe("1M");
    expect(shown("2500000000")).toBe("2.5B");
    expect(shown("3200000000000")).toBe("3.2T");
  });

  it("compacts a grouped number too", () => {
    // Test: Compaction of an already-grouped token.
    // Situation: The agent wrote the figure with thousands separators.
    // Expectation: The separators do not prevent the magnitude being read.
    expect(shown("1,234,567.89")).toBe("1.23M");
  });

  it("leaves six figures spelled out", () => {
    // Test: The compaction threshold.
    // Situation: The token is just under a million.
    // Expectation: Nothing is rewritten -- 999999 is still readable at a
    //   glance.
    expect(formatNumericToken("999999")).toBeNull();
  });

  it("handles negatives on both paths", () => {
    // Test: Sign preservation through rounding and compaction.
    // Situation: A negative long decimal and a negative magnitude.
    // Expectation: Both keep their sign.
    expect(shown("-84.0412195122")).toBe("-84.04");
    expect(shown("-1234567")).toBe("-1.23M");
  });

  it("does not round a real value away to zero", () => {
    // Test: Zero suppression.
    // Situation: A non-zero value smaller than the rounding step.
    // Expectation: The threshold form, not "0.00" -- which would read as
    //   exactly nothing, a different claim.
    expect(shown("0.004")).toBe("< 0.01");
    expect(shown("0.0000001")).toBe("< 0.01");
    expect(shown("-0.004")).toBe("> -0.01");
  });

  it("keeps an exact zero exact", () => {
    // Test: A genuine zero.
    // Situation: The token is 0 or 0.00.
    // Expectation: Nothing is rewritten, so the threshold form never stands in
    //   for a real zero.
    expect(formatNumericToken("0")).toBeNull();
    expect(formatNumericToken("0.00")).toBeNull();
  });

  it("keeps the grouping style the token was written in", () => {
    // Test: Thousands separators are preserved, not introduced.
    // Situation: The same value written with and without separators.
    // Expectation: Each keeps its own style.
    expect(shown("123,456.789")).toBe("123,456.79");
    expect(shown("123456.789")).toBe("123456.79");
  });

  it("carries the unrounded value, grouped for reading", () => {
    // Test: The value behind a shortened figure.
    // Situation: A long decimal and a compacted magnitude.
    // Expectation: `full` is the original, with separators added where they
    //   help.
    expect(formatNumericToken("84.0412195122")?.full).toBe("84.0412195122");
    expect(formatNumericToken("1234567.89")?.full).toBe("1,234,567.89");
  });
});

describe("splitFormattedNumbers", () => {
  it("shortens the numbers in a sentence and leaves the prose", () => {
    // Test: Mixed prose and figures.
    // Situation: One long decimal inside a sentence.
    // Expectation: Three segments -- text, number, text.
    const segments = splitFormattedNumbers(
      "life expectancy is 84.0412195122 years",
    );
    expect(segments[0]).toBe("life expectancy is ");
    expect(segments[1]).toEqual({ display: "84.04", full: "84.0412195122" });
    expect(segments[2]).toBe(" years");
  });

  it("returns the text untouched when there is nothing to shorten", () => {
    // Test: Prose with no figures worth changing.
    // Situation: A sentence containing only a year.
    // Expectation: A single string segment, so no extra elements are made.
    expect(splitFormattedNumbers("In 2023, Japan ranked first.")).toEqual([
      "In 2023, Japan ranked first.",
    ]);
  });

  it("leaves identifiers alone", () => {
    // Test: Digit runs that are part of a word.
    // Situation: A DCID and a version string, both of which the agent writes
    //   in prose as well as in code spans.
    // Expectation: Untouched -- rewriting one corrupts an id.
    expect(splitFormattedNumbers("Count_Person_2023_Male")).toEqual([
      "Count_Person_2023_Male",
    ]);
    expect(splitFormattedNumbers("v1.23456 released")).toEqual([
      "v1.23456 released",
    ]);
  });

  it("keeps a currency symbol and a percent sign in place", () => {
    // Test: Units adjacent to a figure.
    // Situation: A prefixed currency symbol and a suffixed percent sign.
    // Expectation: Only the number changes; the unit stays literal text.
    expect(splitFormattedNumbers("$1234567.00 spent")).toEqual([
      "$",
      { display: "1.23M", full: "1,234,567.00" },
      " spent",
    ]);
    expect(splitFormattedNumbers("12.3456% growth")).toEqual([
      { display: "12.35", full: "12.3456" },
      "% growth",
    ]);
  });

  it("does not mangle an ISO date", () => {
    // Test: A date read as three digit runs.
    // Situation: An ISO date in prose.
    // Expectation: Untouched.
    expect(splitFormattedNumbers("2023-01-15")).toEqual(["2023-01-15"]);
  });
});

describe("isNumericText", () => {
  it("accepts a cell holding one value", () => {
    // Test: Column classification, positive cases.
    // Situation: Cells holding a decimal, a grouped integer, a negative, a
    //   percentage and a currency amount.
    // Expectation: All read as values.
    expect(isNumericText("84.04")).toBe(true);
    expect(isNumericText("1,234")).toBe(true);
    expect(isNumericText("-3")).toBe(true);
    expect(isNumericText("12.5%")).toBe(true);
    expect(isNumericText("$900")).toBe(true);
  });

  it("rejects a cell that says anything else", () => {
    // Test: Column classification, negative cases.
    // Situation: A place name, a value with a trailing unit word, and a range.
    // Expectation: None reads as a single value.
    expect(isNumericText("Japan")).toBe(false);
    expect(isNumericText("84.04 years")).toBe(false);
    expect(isNumericText("2020-2023")).toBe(false);
  });
});

describe("isNeutralText", () => {
  it("treats blanks and placeholders as saying nothing either way", () => {
    // Test: Placeholder handling in column classification.
    // Situation: Empty, "N/A" and an em dash among real figures.
    // Expectation: They neither prove nor disprove a numeric column.
    expect(isNeutralText("")).toBe(true);
    expect(isNeutralText("N/A")).toBe(true);
    expect(isNeutralText("—")).toBe(true);
    expect(isNeutralText("Japan")).toBe(false);
  });
});

describe("isYearText", () => {
  it("recognizes a bare year", () => {
    // Test: The row-label exception to right alignment.
    // Situation: A four-digit year, a year with decimals, and a magnitude.
    // Expectation: Only the bare year counts.
    expect(isYearText("2023")).toBe(true);
    expect(isYearText("1960")).toBe(true);
    expect(isYearText("2023.5")).toBe(false);
    expect(isYearText("84")).toBe(false);
  });
});
