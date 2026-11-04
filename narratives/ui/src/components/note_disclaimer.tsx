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
 * @fileoverview Renders the AI-generated-content disclaimer note.
 */

import { GeminiInfoIcon } from '@/src/components/icons';

interface DisclaimerNoteProps {
  text?: string;
}

/**
 * The AI-content wording under each answer. The prompt box in data_agent.tsx
 * has its own wording (COMPOSER_DISCLAIMER_TEXT).
 */
export const DISCLAIMER_TEXT =
  'Generated with Gemini using data from the Data Commons Knowledge Graph. Think of this report as a starting point for your research, not a definitive final record. While visualizations cite verified third-party datasets, AI can make mistakes—always verify calculations and key findings using the linked primary sources.';

/** Small AI-generated-content disclaimer shown under each answer. */
export function DisclaimerNote({
  text = DISCLAIMER_TEXT,
}: DisclaimerNoteProps) {
  return (
    <section
      className="flex flex-col gap-1.5 self-stretch"
      aria-label="Disclaimer"
    >
      <hr className="border-border" />
      <div className="flex items-start gap-2.5 pt-2.5 text-ai-disclaimer">
        <GeminiInfoIcon size="xs" className="mt-0.5" />
        <p className="text-body-medium">{text}</p>
      </div>
    </section>
  );
}
