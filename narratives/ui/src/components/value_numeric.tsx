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
 * @fileoverview Renders a shortened number that reveals its unrounded value
 * on hover.
 */

import type { ReactNode } from "react";
import {
  splitFormattedNumbers,
  type FormattedNumber,
} from "../utils/format_number";
import { Tooltip } from "./tooltip";

/**
 * A number the renderer shortened, with the original on hover.
 *
 * The dotted underline and help cursor are the only signal that something was
 * taken away; numbers left alone get neither.
 */
export function NumericValue({ value }: { value: FormattedNumber }) {
  return (
    <Tooltip label={`Full value: ${value.full}`}>
      <span
        className="dc-numeric whitespace-nowrap tabular-nums"
        style={{
          cursor: "help",
          textDecoration: "underline dotted",
          textDecorationColor:
            "color-mix(in srgb, currentColor 35%, transparent)",
          textUnderlineOffset: 3,
        }}
      >
        {/* Visually-hidden text rather than an aria-label: a span carries no
            role, and an aria-label on one is not reliably announced. */}
        <span aria-hidden="true">{value.display}</span>
        <span className="sr-only">
          {value.display}, full value {value.full}
        </span>
      </span>
    </Tooltip>
  );
}

/**
 * Renders a run of text with its long numbers shortened, or returns the string
 * untouched when there is nothing to shorten.
 *
 * `keyPrefix` separates one run from the next: a caller splits a paragraph on
 * its citation markers, so the runs become siblings in one array and would
 * otherwise reuse each other's keys.
 */
export function renderNumbers(text: string, keyPrefix = "n"): ReactNode[] {
  const segments = splitFormattedNumbers(text);
  if (segments.length === 1 && typeof segments[0] === "string") {
    return [segments[0]];
  }
  return segments.map((segment, index) =>
    typeof segment === "string" ? (
      segment
    ) : (
      <NumericValue key={`${keyPrefix}-${index}`} value={segment} />
    ),
  );
}
