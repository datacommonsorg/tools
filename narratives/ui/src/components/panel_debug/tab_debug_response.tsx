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
 * @fileoverview Response tab for the turn debug panel: presents answer blocks,
 * numbered provenance citations with accessible Link components, and follow-ups.
 */

import { Link } from '@/src/components/link';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
  formatAnswerBlockHeading,
  formatOutcomeResponseNote,
} from '@/src/components/panel_debug/copy_debug';
import type {
  TurnDebugOutcome,
  TurnDebugResponse,
} from '@/src/components/panel_debug/report_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugField,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';

/** Props for {@link ResponseTab}. */
export interface ResponseTabProps {
  outcome: TurnDebugOutcome;
  response: TurnDebugResponse;
}

/**
 * Renders the assembled response blocks, citations, and follow-up suggestions.
 */
export const ResponseTab = ({ outcome, response }: ResponseTabProps) => {
  const hasBlocks = response.blocks.length > 0;
  const unansweredNote = formatOutcomeResponseNote(outcome, hasBlocks);

  return (
    <div className="flex flex-col gap-2 text-on-surface">
      {unansweredNote && (
        <div
          role="note"
          className="p-3 rounded-lg bg-surface-soft text-body-medium text-on-surface-variant border border-outline break-words"
        >
          {unansweredNote}
        </div>
      )}

      <DebugSection label={DEBUG_SECTION_HEADINGS.answerBlocks}>
        {!hasBlocks ? (
          <p className="text-body-medium text-on-surface-variant">
            {DEBUG_EMPTY_STATE_MESSAGES.answerBlocks}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {response.blocks.map((block) => (
              <div
                key={block.index}
                className="flex flex-col gap-1.5 p-3 rounded-lg bg-surface border border-outline"
              >
                <span className="text-label-small font-medium text-on-surface-variant">
                  {formatAnswerBlockHeading(block.index, block.type)}
                </span>
                {block.type === 'text' && (
                  <pre
                    className={`${DEBUG_MONO_TEXT_CLASSES} text-on-surface whitespace-pre-wrap break-words`}
                  >
                    {block.markdown}
                  </pre>
                )}
                {block.type === 'chart' && (
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-body-medium">
                    <DebugField
                      label="Type"
                      value={block.chart.vizType}
                      valueClassName="font-medium"
                    />
                    <DebugField
                      label="Title"
                      value={block.chart.title ?? DEBUG_PANEL_COPY.noneFallback}
                    />
                    <DebugField
                      label="Places"
                      value={
                        block.chart.placeDcids &&
                        block.chart.placeDcids.length > 0
                          ? block.chart.placeDcids.join(', ')
                          : DEBUG_PANEL_COPY.noneFallback
                      }
                      spanTwo
                      valueClassName={`${DEBUG_MONO_TEXT_CLASSES} break-words`}
                    />
                    <DebugField
                      label="Variables"
                      value={
                        block.chart.variableDcids.length > 0
                          ? block.chart.variableDcids.join(', ')
                          : DEBUG_PANEL_COPY.noneFallback
                      }
                      spanTwo
                      valueClassName={`${DEBUG_MONO_TEXT_CLASSES} break-words`}
                    />
                  </dl>
                )}
              </div>
            ))}
          </div>
        )}
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.citations}>
        {response.provenance.length === 0 ? (
          <p className="text-body-medium text-on-surface-variant">
            {DEBUG_EMPTY_STATE_MESSAGES.citations}
          </p>
        ) : (
          <ol className="list-none flex flex-col gap-2">
            {response.provenance.map((source, index) => {
              const citationNumber = index + 1;
              const title =
                source.dataset ||
                source.name ||
                source.url ||
                DEBUG_PANEL_COPY.unnamedSource;
              return (
                <li
                  key={index}
                  className="flex flex-col gap-0.5 p-3 rounded-lg bg-surface border border-outline text-body-medium"
                >
                  <div className="flex items-baseline gap-2">
                    <span className="text-label-small font-bold text-on-surface-variant shrink-0">
                      {`[${citationNumber}]`}
                    </span>
                    <span className="font-medium text-on-surface break-words">
                      {title}
                    </span>
                  </div>
                  {source.url && (
                    <div className="mt-1">
                      <Link
                        href={source.url}
                        className="min-h-11 inline-flex items-center text-body-medium text-theme-primary hover:underline break-all"
                      >
                        {source.url}
                      </Link>
                    </div>
                  )}
                  {source.license && (
                    <span className="text-caption text-on-surface-variant">
                      {`License: ${source.license}`}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.followUps}>
        {response.followUps.length === 0 ? (
          <p className="text-body-medium text-on-surface-variant">
            {DEBUG_EMPTY_STATE_MESSAGES.followUps}
          </p>
        ) : (
          <ul className="pl-5 flex flex-col gap-1 list-disc text-body-medium">
            {response.followUps.map((question, index) => (
              <li key={index} className="text-on-surface break-words">
                {question}
              </li>
            ))}
          </ul>
        )}
      </DebugSection>
    </div>
  );
};
