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
 * @fileoverview Analysis tab for the turn debug panel: presents analysis
 * specifications, rejected specifications, processing diagnostics, and digests.
 */

import {
  DEBUG_ANALYSIS_LABELS,
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
  formatDiagnosticsHeading,
  formatRejectedSpecsHeading,
  formatTimeoutSeconds,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugField,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type {
  ServerDebugDiagnostic,
  ServerDebugReport,
} from '@/src/types/debug_report';

/** Props for {@link AnalysisTab}. */
export interface AnalysisTabProps {
  serverReport: ServerDebugReport | null;
}

const renderDiagnosticCard = (
  diagnostic: ServerDebugDiagnostic,
  index: number,
) => {
  if (diagnostic.kind === 'step_refusal') {
    return (
      <div
        key={index}
        className="p-3 rounded-lg bg-surface border border-outline flex flex-col gap-2"
      >
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {diagnostic.round !== null && (
            <DebugField
              label={DEBUG_ANALYSIS_LABELS.round}
              value={diagnostic.round}
            />
          )}
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.stepId}
            value={diagnostic.stepId}
          />
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.script}
            value={diagnostic.script}
          />
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.refusalReason}
            value={diagnostic.refusalReason}
          />
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.message}
            value={diagnostic.message}
            spanTwo
          />
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.inputTableIds}
            value={
              diagnostic.inputTableIds.length > 0
                ? diagnostic.inputTableIds.join(', ')
                : DEBUG_PANEL_COPY.noneFallback
            }
          />
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.alternativeSources}
            value={diagnostic.alternativeSourceCount}
          />
          {diagnostic.coverage !== null && (
            <>
              <DebugField
                label={DEBUG_ANALYSIS_LABELS.contributingPlaces}
                value={`${diagnostic.coverage.contributingPlaces} / ${diagnostic.coverage.requestedPlaces}`}
              />
              <DebugField
                label={DEBUG_ANALYSIS_LABELS.coverageRatio}
                value={diagnostic.coverage.coverageRatio}
              />
              {diagnostic.coverage.referenceDate && (
                <DebugField
                  label={DEBUG_ANALYSIS_LABELS.referenceDate}
                  value={diagnostic.coverage.referenceDate}
                />
              )}
              {diagnostic.coverage.missingPlaces.length > 0 && (
                <DebugField
                  label={DEBUG_ANALYSIS_LABELS.missingPlaces}
                  value={diagnostic.coverage.missingPlaces.join(', ')}
                  spanTwo
                />
              )}
              <DebugField
                label={DEBUG_ANALYSIS_LABELS.mixedVintages}
                value={
                  diagnostic.coverage.mixedVintages
                    ? DEBUG_PANEL_COPY.yes
                    : DEBUG_PANEL_COPY.no
                }
              />
            </>
          )}
        </dl>
      </div>
    );
  }

  return (
    <div
      key={index}
      className="p-3 rounded-lg bg-surface border border-outline flex flex-col gap-2"
    >
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {diagnostic.round !== null && (
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.round}
            value={diagnostic.round}
          />
        )}
        <DebugField
          label={DEBUG_ANALYSIS_LABELS.timeoutSeconds}
          value={formatTimeoutSeconds(diagnostic.timeoutSeconds)}
        />
        <DebugField
          label={DEBUG_ANALYSIS_LABELS.message}
          value={diagnostic.message}
          spanTwo
        />
      </dl>
    </div>
  );
};

/**
 * Renders the server-side analysis specification, rejection history,
 * execution diagnostics, and analysis digest.
 */
export const AnalysisTab = ({ serverReport }: AnalysisTabProps) => {
  if (serverReport === null) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.noServerReport}
      </p>
    );
  }

  const hasAnalysisContent =
    serverReport.specification !== null ||
    serverReport.unavailable !== null ||
    serverReport.digest !== null ||
    serverReport.rejectedSpecifications.length > 0 ||
    serverReport.diagnostics.length > 0 ||
    serverReport.scripts.length > 0;

  if (!hasAnalysisContent) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.analysis}
      </p>
    );
  }

  const scriptsValue =
    serverReport.scripts.length > 0
      ? serverReport.scripts.join(', ')
      : DEBUG_PANEL_COPY.noneFallback;

  return (
    <div className="flex flex-col gap-2">
      <DebugSection label={DEBUG_SECTION_HEADINGS.analysisSummary}>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.specificationOrigin}
            value={
              serverReport.specificationOrigin ?? DEBUG_PANEL_COPY.noneFallback
            }
          />
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.scriptsExecuted}
            value={scriptsValue}
          />
          <DebugField
            label={DEBUG_ANALYSIS_LABELS.processingRetries}
            value={serverReport.processingRetries}
          />
        </dl>
      </DebugSection>

      {serverReport.specification !== null && (
        <DebugSection label={DEBUG_SECTION_HEADINGS.acceptedSpecification}>
          <pre
            className={`p-3 rounded-lg bg-surface border border-outline ${DEBUG_MONO_TEXT_CLASSES} overflow-x-auto whitespace-pre-wrap break-words`}
          >
            {JSON.stringify(serverReport.specification, null, 2)}
          </pre>
        </DebugSection>
      )}

      {serverReport.unavailable !== null && (
        <DebugSection label={DEBUG_SECTION_HEADINGS.unavailableReport}>
          <pre
            className={`p-3 rounded-lg bg-surface border border-outline ${DEBUG_MONO_TEXT_CLASSES} overflow-x-auto whitespace-pre-wrap break-words`}
          >
            {JSON.stringify(serverReport.unavailable, null, 2)}
          </pre>
        </DebugSection>
      )}

      {serverReport.rejectedSpecifications.length > 0 && (
        <DebugSection
          label={formatRejectedSpecsHeading(
            serverReport.rejectedSpecifications.length,
          )}
        >
          <div className="flex flex-col gap-3">
            {serverReport.rejectedSpecifications.map((spec, index) => (
              <div
                key={index}
                className="p-3 rounded-lg bg-surface border border-outline flex flex-col gap-2"
              >
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <DebugField
                    label={DEBUG_ANALYSIS_LABELS.round}
                    value={spec.round}
                  />
                  <DebugField
                    label={DEBUG_ANALYSIS_LABELS.reason}
                    value={spec.reason}
                  />
                </dl>
                {spec.errors.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <span className="text-label-small text-on-surface-variant font-medium">
                      {DEBUG_ANALYSIS_LABELS.validationErrors}
                    </span>
                    <ul className="pl-5 text-body-medium">
                      {spec.errors.map((error, errIndex) => (
                        <li key={errIndex}>{error}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {spec.specification !== null && (
                  <pre
                    className={`p-2 rounded ${DEBUG_MONO_TEXT_CLASSES} bg-surface-soft border border-outline overflow-x-auto whitespace-pre-wrap break-words`}
                  >
                    {JSON.stringify(spec.specification, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </DebugSection>
      )}

      {serverReport.diagnostics.length > 0 && (
        <DebugSection
          label={formatDiagnosticsHeading(serverReport.diagnostics.length)}
        >
          <div className="flex flex-col gap-3">
            {serverReport.diagnostics.map(renderDiagnosticCard)}
          </div>
        </DebugSection>
      )}

      {serverReport.digest !== null && (
        <DebugSection label={DEBUG_SECTION_HEADINGS.analysisDigest}>
          <pre
            className={`p-3 rounded-lg bg-surface border border-outline ${DEBUG_MONO_TEXT_CLASSES} overflow-x-auto whitespace-pre-wrap break-words`}
          >
            {JSON.stringify(serverReport.digest, null, 2)}
          </pre>
        </DebugSection>
      )}
    </div>
  );
};
