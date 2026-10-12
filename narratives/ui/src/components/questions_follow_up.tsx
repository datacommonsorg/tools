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
 * @fileoverview Renders clickable follow-up questions that resubmit the query via the onAsk callback.
 */

const COLOR_HEADING = 'var(--color-on-surface)';
const COLOR_LINK = 'var(--color-theme-primary)';
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface FollowUpQuestionsProps {
  questions: string[];
  onAsk?: (question: string) => void;
}

/** Clickable follow-up question suggestions shown after a completed answer. */
export function FollowUpQuestions({
  questions,
  onAsk,
}: FollowUpQuestionsProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <section aria-labelledby="followups-heading" className="mt-2">
      <h2
        id="followups-heading"
        className="font-medium"
        style={{
          fontFamily: '"Google Sans", "Google Sans Text", sans-serif',
          fontSize: 22,
          lineHeight: '28px',
          color: COLOR_HEADING,
          fontWeight: 500,
          margin: 0,
          paddingTop: 12,
        }}
      >
        Follow up questions
      </h2>
      <ul
        className="list-none p-0 m-0 mt-2 flex flex-col gap-1.5"
        style={{
          fontFamily: FONT_STACK,
          fontSize: 16,
          lineHeight: '24px',
          fontWeight: 500,
        }}
      >
        {questions.map((q, i) => (
          <li key={`${q}-${i}`}>
            <button
              type="button"
              onClick={() => onAsk?.(q)}
              className="bg-transparent border-0 p-0 text-left cursor-pointer hover:underline"
              style={{ color: COLOR_LINK, font: 'inherit' }}
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
