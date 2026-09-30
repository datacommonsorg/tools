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
 * @fileoverview Rounds and compacts numbers for on-screen reading, keeping
 * the raw value for the tooltip.
 */

/**
 * Display rounding for the answer body and its tables, after Ehrenberg's
 * two-digit rule. The unrounded value is kept on every shortened token as
 * {@link FormattedNumber.full}.
 */
export const DISPLAY_DECIMALS = 2;

/** Magnitude from which a number reads better compacted than spelled out. */
const COMPACT_FROM = 1_000_000;

/** Compact units, largest first — a value takes the first one it clears. */
const COMPACT_UNITS = [
  { value: 1e12, suffix: "T" },
  { value: 1e9, suffix: "B" },
  { value: 1e6, suffix: "M" },
] as const;

/** A number the renderer shortened, and the value it shortened. */
export interface FormattedNumber {
  /** What the reader sees, e.g. "84.04", "1.23M", "< 0.01". */
  display: string;
  /** The unrounded value, thousands-grouped for reading. */
  full: string;
}

/** A run of text, or a number within it that we shortened. */
export type TextSegment = string | FormattedNumber;

/**
 * One number as it appears in prose. Currency symbols and `%` sit outside the
 * match so they stay put as literal text.
 */
const NUMBER_TOKEN = /-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?/g;

/** A table cell holding one number and nothing else but a unit marker. */
const NUMERIC_CELL =
  /^[-+]?[$£€¥₹]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*%?$/;

/** Placeholders that neither prove nor disprove that a column is numeric. */
const NEUTRAL_CELL = /^(?:|-|–|—|n\/a|na|null|nan)$/i;

/** A bare four-digit year, the one "number" a table uses as a row label. */
const YEAR_CELL = /^(?:1[0-9]|2[0-9])\d{2}$/;

/** True for characters that make a digit run part of a word, not a value. */
function isWordish(char: string | undefined): boolean {
  return char !== undefined && /[A-Za-z0-9_]/.test(char);
}

/** Inserts thousands separators into the integer part of a decimal string. */
function group(value: string): string {
  const negative = value.startsWith("-");
  const digits = negative ? value.slice(1) : value;
  const dot = digits.indexOf(".");
  const whole = dot === -1 ? digits : digits.slice(0, dot);
  const rest = dot === -1 ? "" : digits.slice(dot);
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (negative ? "-" : "") + grouped + rest;
}

/** Drops the trailing zeros `toFixed` adds, and the point left behind. */
function trimZeros(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

/**
 * Shortens one numeric token, or returns null to leave it exactly as written.
 *
 * Null for anything already short enough is what keeps years and ids intact:
 * `2023` is never rewritten as `2,023` or `2.02K`.
 */
export function formatNumericToken(raw: string): FormattedNumber | null {
  const plain = raw.replace(/,/g, "");
  const value = Number(plain);
  if (!Number.isFinite(value)) return null;

  const full = raw.includes(",") ? raw : group(raw);
  const magnitude = Math.abs(value);

  if (magnitude >= COMPACT_FROM) {
    const unit =
      COMPACT_UNITS.find((candidate) => magnitude >= candidate.value) ??
      COMPACT_UNITS[COMPACT_UNITS.length - 1];
    const display =
      trimZeros((value / unit.value).toFixed(DISPLAY_DECIMALS)) + unit.suffix;
    return display === raw ? null : { display, full };
  }

  const point = plain.indexOf(".");
  const decimals = point === -1 ? 0 : plain.length - point - 1;
  // Cap, don't pad: 84.5 stays 84.5 rather than becoming 84.50.
  if (decimals <= DISPLAY_DECIMALS) return null;

  const fixed = value.toFixed(DISPLAY_DECIMALS);
  // "0.00" would read as an exact nothing, which is a different claim. An
  // exact zero is excluded: it rounds away because it *is* zero, so it falls
  // through and is capped like any other figure.
  if (Number(fixed) === 0 && value !== 0) {
    return { display: value > 0 ? "< 0.01" : "> -0.01", full };
  }

  const display = raw.includes(",") ? group(fixed) : fixed;
  return display === raw ? null : { display, full };
}

/**
 * Splits prose into plain runs and the numbers worth shortening.
 *
 * A digit run touching a letter or underscore is skipped: `Count_Person_2023`
 * is an identifier, not a measurement.
 */
export function splitFormattedNumbers(text: string): TextSegment[] {
  const out: TextSegment[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  NUMBER_TOKEN.lastIndex = 0;
  while ((match = NUMBER_TOKEN.exec(text)) !== null) {
    const start = match.index;
    const end = start + match[0].length;
    if (isWordish(text[start - 1]) || isWordish(text[end])) continue;
    const formatted = formatNumericToken(match[0]);
    if (!formatted) continue;
    if (start > last) out.push(text.slice(last, start));
    out.push(formatted);
    last = end;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** True when a cell holds one value — the test for a right-aligned column. */
export function isNumericText(text: string): boolean {
  return NUMERIC_CELL.test(text.trim());
}

/** True when a cell is blank or a placeholder, so says nothing either way. */
export function isNeutralText(text: string): boolean {
  return NEUTRAL_CELL.test(text.trim());
}

/**
 * True for a bare year. A year labels a row rather than measuring anything, so
 * its column is not set right with the figures.
 */
export function isYearText(text: string): boolean {
  return YEAR_CELL.test(text.trim());
}
