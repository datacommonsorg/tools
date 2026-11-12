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
 * @fileoverview TypeScript domain model and wire parser for the server-emitted
 * turn debug report payload.
 */

export type ServerDebugTerminalState = 'complete' | 'refused' | 'error';
export type ServerSourceSelection = 'chosen' | 'server_default' | 'derived';
export type ServerSpecificationOrigin = 'model' | 'default';

export interface ServerDebugTokenCall {
  readonly phase: string;
  readonly model: string;
  readonly round: number | null;
  readonly promptTokenCount: number;
  readonly candidatesTokenCount: number;
  readonly thoughtsTokenCount: number;
  readonly totalTokenCount: number;
}

export interface ServerDebugTokenUsage {
  readonly promptTokenCount: number;
  readonly candidatesTokenCount: number;
  readonly thoughtsTokenCount: number;
  readonly totalTokenCount: number;
  readonly calls: readonly ServerDebugTokenCall[];
}

export interface ServerDebugPlaceRef {
  readonly dcid: string;
  readonly name: string;
}

export interface ServerDebugSource {
  readonly name: string;
  readonly url: string;
  readonly license: string | null;
  readonly dataset: string | null;
  readonly provider: string | null;
  readonly dateRange: string | null;
}

export interface ServerDebugTable {
  readonly tableId: string;
  readonly usedInAnswer: boolean;
  readonly variableDcid: string;
  readonly variableName: string;
  readonly unit: string | null;
  readonly scalingFactor: number | null;
  readonly measurementMethod: string | null;
  readonly observationPeriod: string | null;
  readonly parentPlaceDcid: string | null;
  readonly childPlaceType: string | null;
  readonly placesWithDataCount: number;
  readonly places: readonly ServerDebugPlaceRef[];
  readonly facetId: string | null;
  readonly sourceSelection: ServerSourceSelection;
  readonly source: ServerDebugSource | null;
  readonly dateRange: readonly [string, string] | null;
  readonly rowCount: number;
}

export interface ServerDebugThought {
  readonly phase: 'discovery' | 'synthesis';
  readonly text: string;
  readonly round: number | null;
}

export interface ServerDebugToolCall {
  readonly name: string;
  readonly arguments: Readonly<Record<string, unknown>>;
  readonly status?: 'success' | 'error';
  readonly result?: string;
  readonly round?: number;
  readonly durationMs?: number;
}

export interface ServerDebugRejectedSpec {
  readonly round: number;
  readonly reason: string;
  readonly errors: readonly string[];
  readonly specification: Readonly<Record<string, unknown>> | null;
}

export interface ServerDebugCoverage {
  readonly contributingPlaces: number;
  readonly requestedPlaces: number;
  readonly coverageRatio: number;
  readonly referenceDate: string | null;
  readonly missingPlaces: readonly string[];
  readonly mixedVintages: boolean;
}

export interface ServerDebugStepRefusalDiagnostic {
  readonly kind: 'step_refusal';
  readonly round: number | null;
  readonly stepId: string;
  readonly script: string;
  readonly refusalReason: string;
  readonly message: string;
  readonly inputTableIds: readonly string[];
  readonly coverage: ServerDebugCoverage | null;
  readonly alternativeSourceCount: number;
}

export interface ServerDebugTimeoutDiagnostic {
  readonly kind: 'timeout';
  readonly round: number | null;
  readonly timeoutSeconds: number;
  readonly message: string;
}

export type ServerDebugDiagnostic =
  | ServerDebugStepRefusalDiagnostic
  | ServerDebugTimeoutDiagnostic;

export interface ServerDebugCappedText {
  readonly text: string;
  readonly truncated: boolean;
  readonly totalChars: number;
}

export interface ServerDebugRoleConfig {
  readonly role: string;
  readonly model: string;
  readonly temperature: number;
  readonly thinkingLevel: string;
}

export interface ServerDebugReport {
  readonly turnId: string;
  readonly terminalState: ServerDebugTerminalState;
  readonly terminalReason: string | null;
  readonly isClarification: boolean;
  readonly pattern: string | null;
  readonly durationMs: number;
  readonly phaseDurationsMs: Readonly<Record<string, number>>;
  readonly nestedPhases: Readonly<Record<string, string>>;
  readonly mcpIterations: number;
  readonly scripts: readonly string[];
  readonly processingRetries: number;
  readonly chartsEmitted: number;
  readonly chartsRejected: number;
  readonly tokens: ServerDebugTokenUsage;
  readonly tables: readonly ServerDebugTable[];
  readonly thoughts: readonly ServerDebugThought[];
  readonly toolCalls: readonly ServerDebugToolCall[];
  readonly rejectedSpecifications: readonly ServerDebugRejectedSpec[];
  readonly diagnostics: readonly ServerDebugDiagnostic[];
  readonly specification: Readonly<Record<string, unknown>> | null;
  readonly specificationOrigin: ServerSpecificationOrigin | null;
  readonly unavailable: Readonly<Record<string, unknown>> | null;
  readonly digest: Readonly<Record<string, unknown>> | null;
  readonly synthesisPrompt: ServerDebugCappedText | null;
  readonly synthesisRawOutput: ServerDebugCappedText | null;
  readonly roleConfigs: readonly ServerDebugRoleConfig[];
  readonly promptHashes: Readonly<Record<string, string>>;
  readonly buildSha: string | null;
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readString = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback;

const readNullableString = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null;

const readNumber = (value: unknown, fallback = 0): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback;

const readNullableNumber = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

const readStringArray = (value: unknown): readonly string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];

const readStringRecord = (value: unknown): Readonly<Record<string, string>> => {
  if (!isPlainObject(value)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const [k, v] of Object.entries(value)) {
    if (typeof v === 'string') {
      result[k] = v;
    }
  }
  return result;
};

const readNumberRecord = (value: unknown): Readonly<Record<string, number>> => {
  if (!isPlainObject(value)) {
    return {};
  }
  const result: Record<string, number> = {};
  for (const [k, v] of Object.entries(value)) {
    if (typeof v === 'number' && Number.isFinite(v)) {
      result[k] = v;
    }
  }
  return result;
};

const readObjectOrNull = (
  value: unknown,
): Readonly<Record<string, unknown>> | null =>
  isPlainObject(value) ? value : null;

/**
 * Validates and decodes a raw wire payload into a typed {@link ServerDebugReport}.
 * Returns null if the envelope is invalid.
 */
export const parseServerDebugReport = (
  raw: unknown,
): ServerDebugReport | null => {
  if (!isPlainObject(raw)) {
    return null;
  }
  const turnId = raw.turn_id;
  if (typeof turnId !== 'string' || turnId.length === 0) {
    return null;
  }
  const terminalStateRaw = raw.terminal_state;
  if (
    terminalStateRaw !== 'complete' &&
    terminalStateRaw !== 'refused' &&
    terminalStateRaw !== 'error'
  ) {
    return null;
  }
  const durationMsRaw = raw.duration_ms;
  if (typeof durationMsRaw !== 'number' || !Number.isFinite(durationMsRaw)) {
    return null;
  }
  const tokensRaw = raw.tokens;
  if (!isPlainObject(tokensRaw)) {
    return null;
  }

  const calls: ServerDebugTokenCall[] = Array.isArray(tokensRaw.calls)
    ? tokensRaw.calls.filter(isPlainObject).map((call) => ({
        phase: readString(call.phase),
        model: readString(call.model),
        round: readNullableNumber(call.round),
        promptTokenCount: readNumber(call.prompt_token_count),
        candidatesTokenCount: readNumber(call.candidates_token_count),
        thoughtsTokenCount: readNumber(call.thoughts_token_count),
        totalTokenCount: readNumber(call.total_token_count),
      }))
    : [];

  const tokens: ServerDebugTokenUsage = {
    promptTokenCount: readNumber(tokensRaw.prompt_token_count),
    candidatesTokenCount: readNumber(tokensRaw.candidates_token_count),
    thoughtsTokenCount: readNumber(tokensRaw.thoughts_token_count),
    totalTokenCount: readNumber(tokensRaw.total_token_count),
    calls,
  };

  const tables: ServerDebugTable[] = Array.isArray(raw.tables)
    ? raw.tables.filter(isPlainObject).map((table) => {
        const places: ServerDebugPlaceRef[] = Array.isArray(table.places)
          ? table.places.filter(isPlainObject).map((p) => ({
              dcid: readString(p.dcid),
              name: readString(p.name),
            }))
          : [];

        let source: ServerDebugSource | null = null;
        if (isPlainObject(table.source)) {
          source = {
            name: readString(table.source.name),
            url: readString(table.source.url),
            license: readNullableString(table.source.license),
            dataset: readNullableString(table.source.dataset),
            provider: readNullableString(table.source.provider),
            dateRange: readNullableString(table.source.date_range),
          };
        }

        let dateRange: readonly [string, string] | null = null;
        if (
          Array.isArray(table.date_range) &&
          table.date_range.length === 2 &&
          typeof table.date_range[0] === 'string' &&
          typeof table.date_range[1] === 'string'
        ) {
          dateRange = [table.date_range[0], table.date_range[1]];
        }

        const rawSelection = table.source_selection;
        const sourceSelection: ServerSourceSelection =
          rawSelection === 'chosen' ||
          rawSelection === 'server_default' ||
          rawSelection === 'derived'
            ? rawSelection
            : 'server_default';

        return {
          tableId: readString(table.table_id),
          usedInAnswer: Boolean(table.used_in_answer),
          variableDcid: readString(table.variable_dcid),
          variableName: readString(table.variable_name),
          unit: readNullableString(table.unit),
          scalingFactor: readNullableNumber(table.scaling_factor),
          measurementMethod: readNullableString(table.measurement_method),
          observationPeriod: readNullableString(table.observation_period),
          parentPlaceDcid: readNullableString(table.parent_place_dcid),
          childPlaceType: readNullableString(table.child_place_type),
          placesWithDataCount: readNumber(table.places_with_data_count),
          places,
          facetId: readNullableString(table.facet_id),
          sourceSelection,
          source,
          dateRange,
          rowCount: readNumber(table.row_count),
        };
      })
    : [];

  const thoughts: ServerDebugThought[] = Array.isArray(raw.thoughts)
    ? raw.thoughts.filter(isPlainObject).map((t) => ({
        phase: t.phase === 'discovery' ? 'discovery' : 'synthesis',
        text: readString(t.text),
        round: readNullableNumber(t.round),
      }))
    : [];

  const toolCalls: ServerDebugToolCall[] = Array.isArray(raw.tool_calls)
    ? raw.tool_calls.filter(isPlainObject).map((call) => {
        const status =
          call.status === 'success' || call.status === 'error'
            ? call.status
            : undefined;
        const round = readNullableNumber(call.round);
        const durationMs = readNullableNumber(call.duration_ms);
        const result =
          typeof call.result === 'string' ? call.result : undefined;
        return {
          name: readString(call.name),
          arguments: isPlainObject(call.arguments) ? call.arguments : {},
          ...(status !== undefined ? { status } : {}),
          ...(result !== undefined ? { result } : {}),
          ...(round !== null ? { round } : {}),
          ...(durationMs !== null ? { durationMs } : {}),
        };
      })
    : [];

  const rejectedSpecifications: ServerDebugRejectedSpec[] = Array.isArray(
    raw.rejected_specifications,
  )
    ? raw.rejected_specifications.filter(isPlainObject).map((spec) => ({
        round: readNumber(spec.round),
        reason: readString(spec.reason),
        errors: readStringArray(spec.errors),
        specification: readObjectOrNull(spec.specification),
      }))
    : [];

  const diagnostics: ServerDebugDiagnostic[] = Array.isArray(raw.diagnostics)
    ? raw.diagnostics
        .filter(isPlainObject)
        .flatMap((diag): ServerDebugDiagnostic[] => {
          if (diag.kind === 'step_refusal') {
            let coverage: ServerDebugCoverage | null = null;
            if (isPlainObject(diag.coverage)) {
              coverage = {
                contributingPlaces: readNumber(
                  diag.coverage.contributing_places,
                ),
                requestedPlaces: readNumber(diag.coverage.requested_places),
                coverageRatio: readNumber(diag.coverage.coverage_ratio),
                referenceDate: readNullableString(diag.coverage.reference_date),
                missingPlaces: readStringArray(diag.coverage.missing_places),
                mixedVintages: Boolean(diag.coverage.mixed_vintages),
              };
            }
            return [
              {
                kind: 'step_refusal',
                round: readNullableNumber(diag.round),
                stepId: readString(diag.step_id),
                script: readString(diag.script),
                refusalReason: readString(diag.refusal_reason),
                message: readString(diag.message),
                inputTableIds: readStringArray(diag.input_table_ids),
                coverage,
                alternativeSourceCount: readNumber(
                  diag.alternative_source_count,
                ),
              },
            ];
          }
          if (diag.kind === 'timeout') {
            return [
              {
                kind: 'timeout',
                round: readNullableNumber(diag.round),
                timeoutSeconds: readNumber(diag.timeout_seconds),
                message: readString(diag.message),
              },
            ];
          }
          return [];
        })
    : [];

  let synthesisPrompt: ServerDebugCappedText | null = null;
  if (isPlainObject(raw.synthesis_prompt)) {
    synthesisPrompt = {
      text: readString(raw.synthesis_prompt.text),
      truncated: Boolean(raw.synthesis_prompt.truncated),
      totalChars: readNumber(raw.synthesis_prompt.total_chars),
    };
  }

  let synthesisRawOutput: ServerDebugCappedText | null = null;
  if (isPlainObject(raw.synthesis_raw_output)) {
    synthesisRawOutput = {
      text: readString(raw.synthesis_raw_output.text),
      truncated: Boolean(raw.synthesis_raw_output.truncated),
      totalChars: readNumber(raw.synthesis_raw_output.total_chars),
    };
  }

  const roleConfigs: ServerDebugRoleConfig[] = Array.isArray(raw.role_configs)
    ? raw.role_configs.filter(isPlainObject).map((rc) => ({
        role: readString(rc.role),
        model: readString(rc.model),
        temperature: readNumber(rc.temperature),
        thinkingLevel: readString(rc.thinking_level),
      }))
    : [];

  const rawOrigin = raw.specification_origin;
  const specificationOrigin: ServerSpecificationOrigin | null =
    rawOrigin === 'model' || rawOrigin === 'default' ? rawOrigin : null;

  return {
    turnId,
    terminalState: terminalStateRaw,
    terminalReason: readNullableString(raw.terminal_reason),
    isClarification: Boolean(raw.is_clarification),
    pattern: readNullableString(raw.pattern),
    durationMs: durationMsRaw,
    phaseDurationsMs: readNumberRecord(raw.phase_durations_ms),
    nestedPhases: readStringRecord(raw.nested_phases),
    mcpIterations: readNumber(raw.mcp_iterations),
    scripts: readStringArray(raw.scripts),
    processingRetries: readNumber(raw.processing_retries),
    chartsEmitted: readNumber(raw.charts_emitted),
    chartsRejected: readNumber(raw.charts_rejected),
    tokens,
    tables,
    thoughts,
    toolCalls,
    rejectedSpecifications,
    diagnostics,
    specification: readObjectOrNull(raw.specification),
    specificationOrigin,
    unavailable: readObjectOrNull(raw.unavailable),
    digest: readObjectOrNull(raw.digest),
    synthesisPrompt,
    synthesisRawOutput,
    roleConfigs,
    promptHashes: readStringRecord(raw.prompt_hashes),
    buildSha: readNullableString(raw.build_sha),
  };
};
