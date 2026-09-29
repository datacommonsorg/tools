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

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResponseCard } from "./card_response";
import type { ProvenanceItem } from "../hooks/use_sse_chat";

/**
 * The table work only holds together if react-markdown really does hand each
 * row its cells as elements this component can index, so these render the
 * whole markdown path rather than unit-testing the analysis alone.
 */

const SOURCES: ProvenanceItem[] = [
  { name: "World Development Indicators", url: "https://worldbank.org/wdi" },
];

const TABLE = `
| Year | Life Expectancy (Years) |
| --- | --- |
| 2023 | 84.0412195122 [1] |
| 2022 | 83.9963414634 [1] |
| 2021 | 84.4456097561 [1] |
`;

function renderMarkdown(body: string) {
  return render(<ResponseCard title="q" body={body} sources={SOURCES} bare />);
}

afterEach(cleanup);

describe("ResponseCard tables", () => {
  it("caps the figures at two decimals", () => {
    // Test: Rounding inside a rendered table.
    // Situation: A time series written to eleven decimals.
    // Expectation: The two-decimal form is shown and the long one is gone.
    renderMarkdown(TABLE);
    expect(screen.getByText("84.04")).toBeTruthy();
    expect(screen.queryByText("84.0412195122")).toBeNull();
  });

  it("keeps the unrounded value reachable on the shortened figure", () => {
    // Test: Nothing is lost to rounding.
    // Situation: A figure the renderer shortened.
    // Expectation: Its accessible name carries the full value, so a reader who
    //   cannot hover can still check it against the source.
    const { container } = renderMarkdown(TABLE);
    const shortened = Array.from(container.querySelectorAll("span")).find(
      (node) => node.textContent === "84.04",
    );
    expect(shortened?.getAttribute("aria-label")).toBe(
      "84.04, full value 84.0412195122",
    );
  });

  it("sets the column of figures right and leaves the years left", () => {
    // Test: Column alignment.
    // Situation: A year column beside a value column.
    // Expectation: Only the values are set right.
    const { container } = renderMarkdown(TABLE);
    const firstRow = container.querySelectorAll("tbody tr")[0];
    const cells = firstRow.querySelectorAll("td");
    expect(cells[0].style.textAlign).toBe("");
    expect(cells[1].style.textAlign).toBe("right");
  });

  it("states the column's citation once, on its header", () => {
    // Test: The per-series reference.
    // Situation: Every row of the value column cites [1].
    // Expectation: The marker appears on the header and on no body cell.
    const { container } = renderMarkdown(TABLE);
    const header = container.querySelectorAll("thead th")[1];
    expect(header.textContent).toContain("[1]");
    for (const cell of Array.from(container.querySelectorAll("tbody td"))) {
      expect(cell.textContent).not.toContain("[1]");
    }
  });

  it("leaves per-row markers alone when rows cite different sources", () => {
    // Test: A column with mixed provenance.
    // Situation: One row cites [1] and the next cites [2].
    // Expectation: The markers stay on the rows and the header gains none.
    const { container } = renderMarkdown(`
| Year | Value |
| --- | --- |
| 2023 | 84.04 [1] |
| 2022 | 83.99 [2] |
`);
    const header = container.querySelectorAll("thead th")[1];
    expect(header.textContent).not.toContain("[1]");
    expect(container.querySelectorAll("tbody td")[1].textContent).toContain(
      "[1]",
    );
  });

  it("respects an alignment the markdown asked for", () => {
    // Test: Explicit GFM alignment.
    // Situation: The table declares centered columns.
    // Expectation: The declared alignment wins over the numeric default.
    const { container } = renderMarkdown(`
| Year | Value |
| :---: | :---: |
| 2023 | 84.0412195122 |
`);
    const cells =
      container.querySelectorAll<HTMLTableCellElement>("tbody td");
    expect(cells[1].style.textAlign).toBe("center");
  });
});

describe("ResponseCard prose", () => {
  it("shortens a long decimal in a sentence", () => {
    // Test: Rounding outside a table.
    // Situation: A bolded figure in running text.
    // Expectation: The two-decimal form is shown.
    renderMarkdown("Life expectancy is **84.0412195122** years [1].");
    expect(screen.getByText("84.04")).toBeTruthy();
  });

  it("compacts a figure in the millions", () => {
    // Test: Compaction outside a table.
    // Situation: A population figure with nine digits.
    // Expectation: The compact form is shown.
    renderMarkdown("The population is 125416877 people.");
    expect(screen.getByText("125.42M")).toBeTruthy();
  });

  it("leaves a year in prose alone", () => {
    // Test: The year exception in running text.
    // Situation: A sentence opening on a year.
    // Expectation: The year is unchanged.
    const { container } = renderMarkdown("As of 2023, the figure held.");
    expect(container.textContent).toContain("As of 2023");
  });

  it("shortens numbers on both sides of a citation marker", () => {
    // Test: Keys across separately rendered runs.
    // Situation: Two figures split by a citation marker, so each run is
    //   rendered separately and the pieces end up siblings in one array.
    // Expectation: Both are shortened and React reports no duplicate key.
    const warn = vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = renderMarkdown(
      "It rose from 82.8426829268 [1] to 84.0412195122 [1] over the decade.",
    );
    expect(container.textContent).toContain("82.84");
    expect(container.textContent).toContain("84.04");
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
