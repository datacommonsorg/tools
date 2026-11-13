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
 * @fileoverview User-facing copy for chat turn errors, notices, actions, and
 * reasoning progress.
 */

import type { TurnStatus } from '@/src/hooks/use_sse_chat';

/** Label of the inline button that resubmits a retryable failed turn's query. */
export const RETRY_LABEL = 'Try again';

/** Label of the button at the end of finished reasoning that collapses it. */
export const CLOSE_REASONING_LABEL = 'Close reasoning details';

/** Reasoning header label once the turn has stopped streaming. */
export const REASONING_DONE_LABEL = 'Reasoning details';

/**
 * Reasoning header label for each streaming phase. The server's `status`
 * events move a turn through these phases.
 */
export const REASONING_PHASE_LABELS: Partial<Record<TurnStatus, string>> = {
  classify: 'Understanding your question',
  discovery: 'Querying data tools',
  processing: 'Analyzing data',
  synthesis: 'Synthesizing answer',
};

/** Reasoning header label while streaming in a status with no phase label. */
export const REASONING_DEFAULT_PHASE_LABEL = 'Thinking';

/** Reasoning body shown during classification, before any thought arrives. */
export const REASONING_PLACEHOLDER_CLASSIFY = 'Reviewing your question…';

/** Reasoning body shown while later phases stream with no thoughts. */
export const REASONING_PLACEHOLDER_STREAMING =
  'Searching Data Commons for relevant indicators and observations…';

/** Reasoning body shown for a finished data turn that emitted no thoughts. */
export const REASONING_PLACEHOLDER_DONE =
  'Analyzed the query and retrieved relevant data from Data Commons.';

/**
 * Error message shown when an upstream response other than a permanent HTTP
 * 4xx (for example, 408, 429, or 5xx) prevents the chat stream from opening.
 */
export const HIGH_TRAFFIC_ERROR =
  'Data Commons is experiencing unusually high traffic right now.';

/**
 * Error message shown when an open chat stream ends without a terminal event
 * because the connection dropped mid-turn.
 */
export const INTERRUPTED_TURN_ERROR =
  'The connection was interrupted before Data Commons could finish the answer. Please try again.';

/**
 * Error message shown when the agent rejects the signed conversation history,
 * for example after its signing key changed, and clears earlier signatures.
 */
export const TRANSCRIPT_REJECTED_ERROR =
  'Data Commons started a fresh conversation because earlier messages could not be loaded. Restate any details from previous turns if needed.';

/** Error message shown when a terminal frame settles in `canceled` without an error string. */
export const CANCELED_TURN_ERROR =
  'This answer was canceled before Data Commons finished.';

/** Fallback error message shown when an `error` terminal frame omits `error`. */
export const DEFAULT_TURN_ERROR =
  'Data Commons ran into an unexpected problem. Please try again later.';

/** Fallback notice message shown when a `refused` terminal frame omits `message`. */
export const DEFAULT_REFUSAL_MESSAGE =
  'Data Commons is not able to help with that.';

/**
 * Formats the error message shown when the agent, or a proxy in front of it,
 * rejects a request with an HTTP status before the chat stream opens. The
 * status text is often empty over HTTP/2, so the status line is trimmed.
 */
export const formatHttpError = (status: number, statusText: string): string => {
  const statusLine = `HTTP ${status} ${statusText}`.trim();
  return `Data Commons ran into a server error. ${statusLine}.`;
};
