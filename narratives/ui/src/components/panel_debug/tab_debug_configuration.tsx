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
 * @fileoverview Configuration tab for the turn debug panel: presents server
 * build information, model role settings, and SHA-256 prompt hashes.
 */

import {
  DEBUG_CONFIG_LABELS,
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugField,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type { ServerDebugReport } from '@/src/types/debug_report';

/** Props for {@link ConfigurationTab}. */
export interface ConfigurationTabProps {
  serverReport: ServerDebugReport | null;
}

/**
 * Renders build metadata, active Gemini role configurations, and loaded
 * prompt SHA-256 hashes.
 */
export const ConfigurationTab = ({ serverReport }: ConfigurationTabProps) => {
  if (serverReport === null) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.noServerReport}
      </p>
    );
  }

  const promptEntries = Object.entries(serverReport.promptHashes);

  return (
    <div className="flex flex-col gap-2">
      <DebugSection label={DEBUG_SECTION_HEADINGS.buildInfo}>
        <dl>
          <DebugField
            label={DEBUG_CONFIG_LABELS.buildSha}
            value={serverReport.buildSha ?? DEBUG_PANEL_COPY.noneFallback}
            valueClassName={`${DEBUG_MONO_TEXT_CLASSES} break-all`}
          />
        </dl>
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.roleConfigs}>
        {serverReport.roleConfigs.length === 0 ? (
          <p className="text-body-medium text-on-surface-variant">
            {DEBUG_EMPTY_STATE_MESSAGES.roleConfigs}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {serverReport.roleConfigs.map((config, index) => (
              <div
                key={config.role || index}
                className="p-3 rounded-lg bg-surface border border-outline flex flex-col gap-2"
              >
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <DebugField
                    label={DEBUG_CONFIG_LABELS.role}
                    value={config.role}
                  />
                  <DebugField
                    label={DEBUG_CONFIG_LABELS.model}
                    value={<span className="font-mono">{config.model}</span>}
                  />
                  <DebugField
                    label={DEBUG_CONFIG_LABELS.temperature}
                    value={String(config.temperature)}
                  />
                  <DebugField
                    label={DEBUG_CONFIG_LABELS.thinkingLevel}
                    value={config.thinkingLevel}
                  />
                </dl>
              </div>
            ))}
          </div>
        )}
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.promptHashes}>
        {promptEntries.length === 0 ? (
          <p className="text-body-medium text-on-surface-variant">
            {DEBUG_EMPTY_STATE_MESSAGES.promptHashes}
          </p>
        ) : (
          <dl className="grid grid-cols-1 gap-2">
            {promptEntries.map(([name, hash]) => (
              <DebugField
                key={name}
                label={name}
                value={hash}
                valueClassName={`${DEBUG_MONO_TEXT_CLASSES} break-all`}
              />
            ))}
          </dl>
        )}
      </DebugSection>
    </div>
  );
};
