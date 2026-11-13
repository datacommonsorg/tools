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
 * @fileoverview Renders a button that exports the answer panel to PDF.
 */

import { useRef } from 'react';
import { ExportIcon } from '@/src/components/icons';
import { Tooltip } from '@/src/components/tooltip';

/**
 * Whether the answer panel shows its PDF export controls. Off for now: the
 * export works but is hidden from users. Flip to `true` to bring it back.
 */
export const IS_PDF_EXPORT_ENABLED = false;

interface ExportPdfButtonProps {
  onExport: () => void;
  busy?: boolean;
  label?: string;
}

const COLOR_FILL = 'var(--color-theme-container)';
const COLOR_TEXT = 'var(--color-on-theme-container)';
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/** Tonal "Export PDF" pill that exports the enclosing answer panel to PDF. */
export function ExportPdfButton({
  onExport,
  busy = false,
  label = 'Export PDF',
}: ExportPdfButtonProps) {
  const internalRef = useRef<HTMLButtonElement>(null);

  return (
    <div
      className="flex items-center"
      style={{ height: 48 }}
      data-non-print="true"
    >
      <Tooltip label="Download this answer as a PDF">
        <button
          ref={internalRef}
          type="button"
          onClick={onExport}
          disabled={busy}
          className="inline-flex items-center justify-center cursor-pointer transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60"
          style={{
            backgroundColor: COLOR_FILL,
            color: COLOR_TEXT,
            border: 0,
            borderRadius: 100,
            padding: '10px 16px',
            gap: 8,
            fontFamily: FONT_STACK,
            fontSize: 14,
            lineHeight: '20px',
            fontWeight: 500,
          }}
        >
          <ExportIcon />
          <span>{busy ? 'Preparing…' : label}</span>
        </button>
      </Tooltip>
    </div>
  );
}
