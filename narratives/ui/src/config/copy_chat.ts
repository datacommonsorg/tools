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
 * @fileoverview User-facing copy for chat turn errors, notices, and actions.
 */

/** Label of the inline button that resubmits a retryable failed turn's query. */
export const RETRY_LABEL = 'Try again';

/** Label of the button at the end of finished reasoning that collapses it. */
export const CLOSE_REASONING_LABEL = 'Close reasoning details';

/**
 * Error message shown when an upstream response other than a permanent HTTP
 * 4xx (for example, 408, 429, or 5xx) prevents the chat stream from opening.
 */
export const HIGH_TRAFFIC_ERROR = 'We are experiencing unusually high traffic.';

/**
 * Error message shown when an open chat stream ends without a terminal event
 * because the connection dropped mid-turn.
 */
export const INTERRUPTED_TURN_ERROR =
  'The connection was interrupted before the response finished.';

/**
 * Error message shown when the agent rejects the signed conversation history,
 * for example after its signing key changed, and clears earlier signatures.
 */
export const TRANSCRIPT_REJECTED_ERROR =
  'The conversation history could not be verified, so earlier context was cleared.';

/** Error message shown when a terminal frame settles in `canceled` without an error string. */
export const CANCELED_TURN_ERROR =
  'The response was canceled before it finished.';

/** Fallback error message shown when an `error` terminal frame omits `error`. */
export const DEFAULT_TURN_ERROR = 'The response failed.';

/** Fallback notice message shown when a `refused` terminal frame omits `message`. */
export const DEFAULT_REFUSAL_MESSAGE = 'The request was declined.';

/**
 * Formats the error message shown when the agent, or a proxy in front of it,
 * rejects a request with an HTTP status before the chat stream opens.
 */
export const formatHttpError = (status: number, statusText: string): string =>
  `HTTP ${status} ${statusText}`;
