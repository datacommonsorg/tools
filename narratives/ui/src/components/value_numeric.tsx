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
 * A number the renderer rounded or compacted, carrying the original underneath.
 *
 * The dotted underline and the help cursor are the only signal that anything
 * was taken away; without them a reader has no reason to hover, and the raw
 * value -- the thing they need to check a figure against its source -- is
 * effectively hidden rather than merely tucked away. Numbers we left alone get
 * neither, so the marking means something.
 *
 * Nothing here reaches the data: the chart's own Download and API code hand
 * back what the data plane served, at the precision it served it.
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
        {/* A reader who cannot hover cannot reach the value the rounding took
            away, so it is in the text too. Visually-hidden rather than an
            aria-label: a span carries no role, and an aria-label on one is not
            reliably announced. */}
        <span aria-hidden="true">{value.display}</span>
        <span className="sr-only">
          {value.display}, full value {value.full}
        </span>
      </span>
    </Tooltip>
  );
}

/**
 * Renders a run of text with its long numbers shortened.
 *
 * Returns the string untouched when there is nothing to shorten, so prose with
 * no figures in it costs no extra elements.
 *
 * `keyPrefix` distinguishes one run from the next. The caller splits a
 * paragraph on its citation markers and renders each run through here, so the
 * pieces end up siblings in one array: without a per-run prefix the second
 * run's first number would reuse the first run's key.
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
