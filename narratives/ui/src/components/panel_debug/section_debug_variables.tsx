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
 * @fileoverview Debug panel section listing the statistical variables a turn
 * referenced.
 */

import {
  DEBUG_SECTION_HEADINGS,
  RESOLVED_DURING_SEARCH_NOTE,
  VARIABLE_NAME_SEPARATOR,
} from '@/src/components/panel_debug/copy_debug';
import { DebugSection } from '@/src/components/panel_debug/section_debug';
import type { VariableUse } from '@/src/utils/inspect_turn';

interface VariablesSectionProps {
  variables: VariableUse[];
}

/**
 * Lists each variable's DCID and display name, noting the variables that
 * were found but never fetched. Renders nothing without variables.
 */
export const VariablesSection = ({ variables }: VariablesSectionProps) => {
  if (variables.length === 0) {
    return null;
  }
  return (
    <DebugSection label={DEBUG_SECTION_HEADINGS.variables}>
      <ul className="m-0 p-0 list-none flex flex-col gap-1">
        {variables.map((variable) => (
          <li key={variable.dcid} className="text-body-medium">
            <span className="font-mono">{variable.dcid}</span>
            {variable.name && (
              <span className="text-on-surface-variant">
                {VARIABLE_NAME_SEPARATOR}
                {variable.name}
              </span>
            )}
            {!variable.fetched && (
              // Variable was resolved during search without fetching
              // observations for it.
              <span className="text-on-surface-variant">
                {RESOLVED_DURING_SEARCH_NOTE}
              </span>
            )}
          </li>
        ))}
      </ul>
    </DebugSection>
  );
};
