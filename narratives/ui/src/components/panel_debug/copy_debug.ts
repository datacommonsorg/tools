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
  yes: 'Yes',
  no: 'No',
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
  analysis: 'Analysis',
  synthesis: 'Synthesis',
  response: 'Response',
  timing: 'Timing',
  tokens: 'Tokens',
  configuration: 'Configuration',
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
  analysisSummary: 'Analysis summary',
  acceptedSpecification: 'Accepted specification',
  unavailableReport: 'Unavailable report',
  analysisDigest: 'Analysis digest',
  synthesisPrompt: 'Synthesis prompt',
  synthesisRawOutput: 'Raw synthesis output',
  synthesisThoughts: 'Synthesis thoughts',
  buildInfo: 'Build info',
  roleConfigs: 'Role configurations',
  promptHashes: 'Prompt hashes',
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
  analysis: 'No analysis specification or results were recorded for this turn.',
  synthesis: 'No synthesis prompt or output was recorded for this turn.',
  roleConfigs: 'No role configurations were recorded for this turn.',
  promptHashes: 'No prompt hashes were recorded for this turn.',
} as const;

/** Field labels on analysis and diagnostic views. */
export const DEBUG_ANALYSIS_LABELS = {
  specificationOrigin: 'Specification origin',
  scriptsExecuted: 'Scripts executed',
  processingRetries: 'Processing retries',
  round: 'Round',
  reason: 'Reason',
  validationErrors: 'Validation errors',
  stepId: 'Step ID',
  script: 'Script',
  refusalReason: 'Refusal reason',
  message: 'Message',
  inputTableIds: 'Input tables',
  alternativeSources: 'Alternative sources',
  coverageRatio: 'Coverage ratio',
  contributingPlaces: 'Places contributing',
  referenceDate: 'Reference date',
  missingPlaces: 'Missing places',
  mixedVintages: 'Mixed vintages',
  timeoutSeconds: 'Timeout duration',
} as const;

/** Field labels on the configuration view. */
export const DEBUG_CONFIG_LABELS = {
  buildSha: 'Build SHA',
  role: 'Role',
  model: 'Model',
  temperature: 'Temperature',
  thinkingLevel: 'Thinking level',
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

/** Formats the heading for a single discovery round in the trajectory tab. */
export const formatDiscoveryRoundHeading = (round: number): string =>
  `Discovery round ${round}`;

/** Returns the rejected specifications section heading. */
export const formatRejectedSpecsHeading = (count: number): string =>
  `Rejected specifications (${count})`;

/** Returns the diagnostics section heading. */
export const formatDiagnosticsHeading = (count: number): string =>
  `Processing diagnostics (${count})`;

/** Formats character count metadata. */
export const formatCharacterCount = (chars: number): string =>
  `${chars.toLocaleString()} characters`;

/** Formats the server truncation notice reporting captured vs total characters. */
export const formatServerTruncationNotice = (
  captured: number,
  total: number,
): string =>
  `Server capped: showing ${captured.toLocaleString()} of ${total.toLocaleString()} characters`;

/** Formats the toggle button label between preview and full text. */
export const formatToggleFullTextLabel = (
  isExpanded: boolean,
  target: string,
): string => (isExpanded ? 'Show preview' : `Show full ${target}`);

/** Formats the copy button label for full text. */
export const formatCopyFullTextLabel = (target: string): string =>
  `Copy full ${target}`;

/** Target labels for synthesis preview and copy actions. */
export const DEBUG_SYNTHESIS_TARGETS = {
  prompt: 'prompt',
  output: 'output',
} as const;

/** Formats a diagnostic timeout duration in seconds. */
export const formatTimeoutSeconds = (seconds: number): string => `${seconds}s`;
