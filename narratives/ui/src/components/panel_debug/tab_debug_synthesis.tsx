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
 * @fileoverview Synthesis tab for the turn debug panel: presents rendered
 * synthesis prompts and raw model outputs with preview truncation and full-text
 * copy actions.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
  DEBUG_SYNTHESIS_TARGETS,
  formatCharacterCount,
  formatCopyFullTextLabel,
  formatServerTruncationNotice,
  formatToggleFullTextLabel,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type {
  ServerDebugCappedText,
  ServerDebugReport,
} from '@/src/types/debug_report';

/** Maximum character length shown in truncated preview mode. */
export const SYNTHESIS_PREVIEW_CHAR_LIMIT = 1_200;

const RESET_DELAY_MS = 2_000;

type CopyStatus = 'idle' | 'copied' | 'failed';

interface SynthesisSectionProps {
  label: string;
  field: ServerDebugCappedText;
  targetName: string;
}

const SynthesisSection = ({
  label,
  field,
  targetName,
}: SynthesisSectionProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copyStatus, setCopyStatus] = useState<CopyStatus>('idle');
  const copyTimerRef = useRef<number | null>(null);

  const clearCopyTimer = useCallback(() => {
    if (copyTimerRef.current !== null) {
      window.clearTimeout(copyTimerRef.current);
      copyTimerRef.current = null;
    }
  }, []);

  const showCopyStatus = useCallback(
    (status: 'copied' | 'failed') => {
      clearCopyTimer();
      setCopyStatus(status);
      copyTimerRef.current = window.setTimeout(() => {
        setCopyStatus('idle');
        copyTimerRef.current = null;
      }, RESET_DELAY_MS);
    },
    [clearCopyTimer],
  );

  useEffect(() => {
    return () => {
      clearCopyTimer();
    };
  }, [clearCopyTimer]);

  const handleCopy = async () => {
    if (typeof navigator.clipboard?.writeText !== 'function') {
      showCopyStatus('failed');
      return;
    }
    try {
      await navigator.clipboard.writeText(field.text);
      showCopyStatus('copied');
    } catch {
      showCopyStatus('failed');
    }
  };

  const shouldTruncate = field.text.length > SYNTHESIS_PREVIEW_CHAR_LIMIT;
  const displayedText =
    shouldTruncate && !isExpanded
      ? field.text.slice(0, SYNTHESIS_PREVIEW_CHAR_LIMIT)
      : field.text;

  const copyStatusMessage =
    copyStatus === 'copied'
      ? DEBUG_PANEL_COPY.copiedStatus
      : copyStatus === 'failed'
        ? DEBUG_PANEL_COPY.copyFailedStatus
        : null;

  return (
    <DebugSection label={label}>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-0.5 text-label-small text-on-surface-variant">
          <span>{formatCharacterCount(field.totalChars)}</span>
          {field.truncated && (
            <span className="font-medium text-error-strong">
              {formatServerTruncationNotice(
                field.text.length,
                field.totalChars,
              )}
            </span>
          )}
        </div>

        <pre
          className={`p-3 rounded-lg bg-surface border border-outline ${DEBUG_MONO_TEXT_CLASSES} overflow-x-auto whitespace-pre-wrap break-words`}
        >
          {displayedText}
        </pre>

        <div className="flex flex-wrap items-center gap-3">
          {shouldTruncate && (
            <button
              type="button"
              aria-expanded={isExpanded}
              onClick={() => setIsExpanded((prev) => !prev)}
              className="min-h-11 inline-flex items-center text-label-large text-theme-primary"
            >
              {formatToggleFullTextLabel(isExpanded, targetName)}
            </button>
          )}
          <button
            type="button"
            onClick={handleCopy}
            className="min-h-11 inline-flex items-center text-label-large text-theme-primary"
          >
            {formatCopyFullTextLabel(targetName)}
          </button>
          {copyStatusMessage !== null && (
            <span
              aria-live="polite"
              className="text-label-small text-on-surface-variant font-mono"
            >
              {copyStatusMessage}
            </span>
          )}
        </div>
      </div>
    </DebugSection>
  );
};

/** Props for {@link SynthesisTab}. */
export interface SynthesisTabProps {
  serverReport: ServerDebugReport | null;
}

/**
 * Renders the rendered synthesis prompt and raw model response, with
 * truncated previews and copy-to-clipboard actions.
 */
export const SynthesisTab = ({ serverReport }: SynthesisTabProps) => {
  if (serverReport === null) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.noServerReport}
      </p>
    );
  }

  if (
    serverReport.synthesisPrompt === null &&
    serverReport.synthesisRawOutput === null
  ) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.synthesis}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {serverReport.synthesisPrompt !== null && (
        <SynthesisSection
          label={DEBUG_SECTION_HEADINGS.synthesisPrompt}
          field={serverReport.synthesisPrompt}
          targetName={DEBUG_SYNTHESIS_TARGETS.prompt}
        />
      )}
      {serverReport.synthesisRawOutput !== null && (
        <SynthesisSection
          label={DEBUG_SECTION_HEADINGS.synthesisRawOutput}
          field={serverReport.synthesisRawOutput}
          targetName={DEBUG_SYNTHESIS_TARGETS.output}
        />
      )}
    </div>
  );
};
