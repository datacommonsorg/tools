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
 * @fileoverview Presentational pieces shared by the debug panel's sections:
 * the labeled section wrapper and the key/value detail.
 */

import type { ReactNode } from 'react';

/**
 * Classes for monospaced body text. `.text-body-medium` is unlayered CSS in
 * index.css and sets its own font family, so it outranks the layered
 * `font-mono` utility on the same element; the important modifier restores the
 * monospaced family.
 */
export const DEBUG_MONO_TEXT_CLASSES = 'text-body-medium font-mono!';

interface DebugSectionProps {
  label: string;
  children: ReactNode;
}

/** Section wrapper: a small uppercase label above its content. */
export const DebugSection = ({ label, children }: DebugSectionProps) => {
  return (
    <section className="flex flex-col gap-1.5">
      <h4 className="m-0 text-label-large uppercase tracking-wide text-on-surface-variant">
        {label}
      </h4>
      {children}
    </section>
  );
};

interface DebugDetailProps {
  label: string;
  value?: string | number;
}

/** One key/value pair on a facet's detail line; renders nothing without a value. */
export const DebugDetail = ({ label, value }: DebugDetailProps) => {
  if (value === undefined || value === '') {
    return null;
  }
  return (
    <span className="text-body-medium text-on-surface-variant">
      {label} <span className="font-mono">{value}</span>
    </span>
  );
};
