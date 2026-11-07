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
 * @fileoverview Renders a failed turn's error notice with an optional inline retry button.
 */

import { RETRY_LABEL } from '@/src/config/copy_chat';

interface ErrorNoticeProps {
  message: string;
  /** Sends the turn's question again; the retry button is omitted when unset. */
  onRetry?: () => void;
}

/**
 * A failed turn's error message, followed by an inline retry button when
 * sending the same question again can succeed.
 */
export function ErrorNotice({ message, onRetry }: ErrorNoticeProps) {
  return (
    <div
      data-testid="turn-error-notice"
      className="self-start px-4 py-3 rounded-2xl bg-error-surface text-error-strong text-body-large max-w-4xl"
    >
      {message}
      {onRetry && (
        <>
          {' '}
          {/* The pseudo-element extends the hit area to 44px tall around the
              inline label without changing the line's layout. */}
          <button
            type="button"
            onClick={onRetry}
            className="relative underline hover:opacity-80 after:absolute after:-inset-x-1 after:-inset-y-2.5"
          >
            {RETRY_LABEL}
          </button>
        </>
      )}
    </div>
  );
}
