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
 * @fileoverview User-visible copy, section headings, and detail labels for the
 * turn debug panel and its tabs.
 */

import type { TurnDebugOutcome } from '@/src/components/panel_debug/report_debug';

/** Text of the panel chrome: the open button, the dialog, and its close button. */
export const DEBUG_PANEL_COPY = {
  openButtonLabel: 'Inspect turn debug details',
  openButtonTitle: 'Inspect turn debug details',
  title: 'Turn debug',
  closeButtonLabel: 'Close turn debug panel',
  closeButtonGlyph: '×',
  copyJsonButtonLabel: 'Copy JSON',
  copiedStatus: 'Copied',
  copyFailedStatus: 'Copy failed',
  tablistAriaLabel: 'Turn debug sections',
  noneFallback: 'None',
  notRecordedFallback: 'Not recorded',
  unnamedSource: 'Unnamed source',
  serverTurnDuration: 'Server turn duration',
} as const;

/** User-facing labels for timing milestones. */
export const DEBUG_MILESTONE_LABELS = {
  headersReceivedMs: 'Headers received',
  firstThoughtMs: 'First thought',
  firstBlockMs: 'First answer block',
  terminalMs: 'Terminal frame',
  followUpsMs: 'Follow-up suggestions',
  totalMs: 'Total duration',
} as const;

/** Usage status labels for a cached table. */
export const DEBUG_TABLE_USAGE_LABELS = {
  used: 'Used in answer',
  unused: 'Unused',
} as const;

/** Scope line field labels for a cached table. */
export const DEBUG_TABLE_SCOPE_LABELS = {
  scope: 'Scope:',
  places: 'Places:',
} as const;

/** User-facing labels for each tab in DebugTabs. */
export const DEBUG_TAB_LABELS = {
  overview: 'Overview',
  data: 'Data',
  trajectory: 'Trajectory',
  response: 'Response',
  timing: 'Timing',
  tokens: 'Tokens',
} as const;

/** Headings of the panel's body sections. */
export const DEBUG_SECTION_HEADINGS = {
  userQuery: 'User query',
  turnIdentifiers: 'Turn identifiers',
  turnOutcome: 'Turn outcome',
  summaryCounts: 'Summary counts',
  conversationContext: 'Conversation context',
  tokenTotals: 'Token totals',
  serverTimings: 'Server timings',
  answerBlocks: 'Answer blocks',
  citations: 'Citations',
  followUps: 'Follow-up suggestions',
  submissionTime: 'Submission time',
  milestones: 'Milestones',
} as const;

/** Empty-state messages for debug tabs. */
export const DEBUG_EMPTY_STATE_MESSAGES = {
  noServerReport: 'No server debug report was received for this turn.',
  dataTables: 'No tables were recorded for this turn.',
  tokenCalls: 'No token calls were recorded for this turn.',
  trajectory: 'No thoughts or tool calls were recorded for this turn.',
  answerBlocks: 'No answer blocks were recorded for this turn.',
  citations: 'No citations were recorded for this turn.',
  followUps: 'No follow-up suggestions were recorded for this turn.',
  timing: 'No client timings were recorded for this turn.',
} as const;

/** Fallback provenance name for a facet without a title or label. */
export const UNNAMED_SOURCE_LABEL = '(unnamed source)';

/** Detail labels on a single facet or table. */
export const DEBUG_FACET_DETAIL_LABELS = {
  coverage: 'coverage',
  observations: 'observations',
  unit: 'unit',
  scalingFactor: 'scaling factor',
  measurementMethod: 'method',
  observationPeriod: 'period',
  facet: 'facet',
  license: 'license',
} as const;

/** Separator between a variable's DCID and its display name. */
export const VARIABLE_NAME_SEPARATOR = ' — ';

/** Marker appended to a tool call that finished with an error. */
export const TOOL_CALL_ERROR_MARKER = ' · error';

/** Returns the token calls section heading for count calls. */
export const formatTokenCallsHeading = (count: number): string =>
  `Token calls (${count})`;

/** Returns the cached tables section heading for count tables. */
export const formatCachedTablesHeading = (count: number): string =>
  `Cached tables (${count})`;

/** Formats a server phase label, noting when it is nested within a parent phase. */
export const formatServerPhaseLabel = (
  phase: string,
  parentPhase?: string,
): string => (parentPhase ? `${phase} (nested in ${parentPhase})` : phase);

/** Formats an optional round number for a token call. */
export const formatRoundLabel = (round: number): string => `round ${round}`;

/** Formats a child-place table scope summary with place count with data. */
export const formatChildScopeSummary = (
  childPlaceType: string,
  parentPlaceDcid: string,
  placesWithDataCount: number,
): string =>
  `${childPlaceType} in ${parentPlaceDcid} (${placesWithDataCount.toLocaleString()} with data)`;

/** Formats table date range or falls back to source date range. */
export const formatTableCoverage = (
  dateRange: readonly [string, string] | null,
  fallback?: string | null,
): string | undefined => {
  if (dateRange) {
    const [start, end] = dateRange;
    return start === end ? start : `${start}..${end}`;
  }
  return fallback ?? undefined;
};

/** Formats a place reference for table displays. */
export const formatPlaceRef = (place: {
  dcid: string;
  name?: string;
}): string =>
  place.name && place.name !== place.dcid
    ? `${place.name} (${place.dcid})`
    : place.dcid;

/** Returns the tool calls section heading for count calls. */
export const formatToolCallsHeading = (count: number): string =>
  `Tool calls (${count})`;

/**
 * Returns the label of a tool call's raw response toggle, naming the action
 * it performs and the response length in characters.
 */
export const formatRawResponseToggleLabel = (
  isOpen: boolean,
  characterCount: number,
): string =>
  `${isOpen ? 'Hide' : 'Show'} raw response (${characterCount.toLocaleString()} chars)`;

/** Formats an elapsed duration in milliseconds for display. */
export const formatDurationMs = (durationMs: number): string =>
  `${Math.round(durationMs).toLocaleString()} ms`;

/** Formats thoughts section heading with count. */
export const formatThoughtsHeading = (count: number): string =>
  `Thoughts (${count})`;

/** Formats answer block heading with index and type. */
export const formatAnswerBlockHeading = (index: number, type: string): string =>
  `Block ${index} (${type})`;

/** Formats the advisory note message for an outcome in ResponseTab. */
export const formatOutcomeResponseNote = (
  outcome: TurnDebugOutcome,
  hasBlocks: boolean,
): string | null => {
  switch (outcome.kind) {
    case 'stopped':
      return 'This turn was stopped per your request.';
    case 'refused':
      return `This turn was refused: ${outcome.message}`;
    case 'error':
      return `This turn terminated with an error: ${outcome.error}`;
    case 'in_progress':
      return `This turn is currently in progress (${outcome.phase}).`;
    case 'done':
      return hasBlocks ? null : 'This turn completed without answer blocks.';
  }
};
