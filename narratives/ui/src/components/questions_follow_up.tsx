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

interface FollowUpQuestionsProps {
  questions: string[];
  onAsk?: (question: string) => void;
  /**
   * False when the answer found no data, so the suggestions are alternatives
   * to the question asked rather than follow-ups to an answer.
   */
  hasData?: boolean;
}

/** Clickable follow-up question suggestions shown after a completed answer. */
export function FollowUpQuestions({
  questions,
  onAsk,
  hasData = true,
}: FollowUpQuestionsProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <section aria-labelledby="followups-heading" className="mt-2">
      <h2
        id="followups-heading"
        className="pt-3 pb-4 mb-4 border-b border-border text-title-large-emphasized text-on-surface"
      >
        {hasData ? 'Follow up questions' : 'Alternative questions'}
      </h2>
      {/* No gap between items: each button's vertical padding creates the touch target spacing. */}
      <ul className="list-disc flex flex-col text-body-medium-emphasized">
        {questions.map((q, i) => (
          <li key={`${q}-${i}`} className="ml-6 text-theme-primary">
            <button
              type="button"
              onClick={() => onAsk?.(q)}
              className="block py-1 text-left hover:underline"
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
