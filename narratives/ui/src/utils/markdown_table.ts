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

/**
 * @fileoverview Reads a markdown table's AST to find its numeric columns and
 * its per-column citations.
 */

import { isNeutralText, isNumericText, isYearText } from "./format_number";

/**
 * The part of an HTML AST node this module reads. Declared locally rather
 * than imported from the `hast` types, so the analysis is testable from an
 * object literal.
 */
export interface MarkdownNode {
  type?: string;
  tagName?: string;
  value?: string;
  children?: MarkdownNode[];
}

/** A `[n]` citation marker, matching the range chip_citation renders. */
const CITATION_MARKER = /\[(\d{1,2})\]/g;

/** What the table renderer needs to know that a single cell cannot tell it. */
export interface TableAnalysis {
  /** Columns whose body cells are all values — these are set right. */
  numericColumns: ReadonlySet<number>;
  /**
   * Citations lifted out of a column's cells onto its header. Only columns
   * whose every cell agreed, so one citing different sources per row keeps
   * its per-row markers.
   */
  hoistedCitations: ReadonlyMap<number, number[]>;
}

/** Concatenates every text node under `node`. */
export function textOf(node: MarkdownNode | undefined): string {
  if (!node) return "";
  if (typeof node.value === "string") return node.value;
  return (node.children ?? []).map(textOf).join("");
}

/** The citation numbers in `text`, in the order they appear. */
export function citationsIn(text: string): number[] {
  const out: number[] = [];
  let match: RegExpExecArray | null;
  CITATION_MARKER.lastIndex = 0;
  while ((match = CITATION_MARKER.exec(text)) !== null) {
    out.push(Number(match[1]));
  }
  return out;
}

/** True when `node` is an element with the given tag. */
function isTag(node: MarkdownNode, tagName: string): boolean {
  return node.type === "element" && node.tagName === tagName;
}

/** The cells of every row in a table section, flattened past thead/tbody. */
function rowsOf(
  node: MarkdownNode,
  section: "thead" | "tbody",
): MarkdownNode[][] {
  const rows: MarkdownNode[][] = [];
  const collect = (row: MarkdownNode) => {
    if (!isTag(row, "tr")) return;
    rows.push(
      (row.children ?? []).filter(
        (cell) => isTag(cell, "td") || isTag(cell, "th"),
      ),
    );
  };
  for (const child of node.children ?? []) {
    if (isTag(child, section)) (child.children ?? []).forEach(collect);
    // A bare <tr> under <table> has no header semantics, so it is a body row.
    else if (section === "tbody" && isTag(child, "tr")) collect(child);
  }
  return rows;
}

/**
 * Works out which columns hold values and which carry one shared citation.
 * Both answers need the whole column, which a single cell cannot see.
 */
export function analyzeMarkdownTable(
  node: MarkdownNode | undefined,
): TableAnalysis {
  const numericColumns = new Set<number>();
  const hoistedCitations = new Map<number, number[]>();
  if (!node) return { numericColumns, hoistedCitations };

  const bodyRows = rowsOf(node, "tbody");
  if (bodyRows.length === 0) return { numericColumns, hoistedCitations };
  const columnCount = Math.max(...bodyRows.map((row) => row.length));

  for (let column = 0; column < columnCount; column++) {
    const cells = bodyRows
      .map((row) => textOf(row[column]))
      .filter((text) => text.trim() !== "");
    if (cells.length === 0) continue;

    // Citations first: the markers have to come off before the rest of the
    // cell can be judged a number.
    const values = cells.map((text) =>
      text.replace(CITATION_MARKER, "").trim(),
    );
    const citations = cells
      .filter((_, i) => !isNeutralText(values[i]))
      .map(citationsIn);
    const key = citations[0]?.join(",") ?? "";
    if (
      citations.length > 0 &&
      key !== "" &&
      citations.every((list) => list.join(",") === key)
    ) {
      hoistedCitations.set(column, citations[0]);
    }

    const numeric = values.filter((text) => isNumericText(text));
    const undecided = values.filter((text) => isNeutralText(text));
    const measurements = numeric.filter((text) => !isYearText(text));
    if (
      numeric.length > 0 &&
      measurements.length > 0 &&
      numeric.length + undecided.length === values.length
    ) {
      numericColumns.add(column);
    }
  }

  return { numericColumns, hoistedCitations };
}
