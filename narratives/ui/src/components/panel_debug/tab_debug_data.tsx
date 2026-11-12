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
 * @fileoverview Data tab for the turn debug panel: lists cached observation tables,
 * their variable mappings, geographic scope, facet details, and source provenance.
 */

import { Link } from '@/src/components/link';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_FACET_DETAIL_LABELS,
  DEBUG_TABLE_SCOPE_LABELS,
  DEBUG_TABLE_USAGE_LABELS,
  formatCachedTablesHeading,
  formatChildScopeSummary,
  formatPlaceRef,
  formatTableCoverage,
  UNNAMED_SOURCE_LABEL,
  VARIABLE_NAME_SEPARATOR,
} from '@/src/components/panel_debug/copy_debug';
import {
  DebugDetail,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type {
  ServerDebugReport,
  ServerDebugTable,
} from '@/src/types/debug_report';

/** Props for {@link DataTab}. */
export interface DataTabProps {
  serverReport: ServerDebugReport | null;
}

/**
 * Renders an individual cached table card.
 */
const CachedTableCard = ({ table }: { table: ServerDebugTable }) => {
  const coverage = formatTableCoverage(
    table.dateRange,
    table.source?.dateRange ?? null,
  );
  const sourceName = table.source?.name || UNNAMED_SOURCE_LABEL;
  const showDataset =
    Boolean(table.source?.dataset) && table.source?.dataset !== sourceName;
  const showProvider =
    Boolean(table.source?.provider) &&
    table.source?.provider !== sourceName &&
    table.source?.provider !== table.source?.dataset;

  return (
    <li className="p-3 rounded-lg bg-surface border border-outline flex flex-col gap-1.5 text-body-medium">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono font-medium text-on-surface">
          {table.tableId}
        </span>
        <div className="flex items-center gap-2 text-label-small">
          <span
            className={
              table.usedInAnswer
                ? 'text-theme-primary font-medium'
                : 'text-on-surface-variant'
            }
          >
            {table.usedInAnswer
              ? DEBUG_TABLE_USAGE_LABELS.used
              : DEBUG_TABLE_USAGE_LABELS.unused}
          </span>
          <span className="text-outline">·</span>
          <span className="text-on-surface-variant">
            {table.sourceSelection}
          </span>
        </div>
      </div>

      <div className="text-body-medium text-on-surface">
        <span className="font-mono">{table.variableDcid}</span>
        {table.variableName.length > 0 && (
          <span>{`${VARIABLE_NAME_SEPARATOR}${table.variableName}`}</span>
        )}
      </div>

      {table.parentPlaceDcid && table.childPlaceType && (
        <div className="text-body-medium text-on-surface-variant">
          <span className="text-label-small text-on-surface-variant">
            {DEBUG_TABLE_SCOPE_LABELS.scope}{' '}
          </span>
          <span>
            {formatChildScopeSummary(
              table.childPlaceType,
              table.parentPlaceDcid,
              table.placesWithDataCount,
            )}
          </span>
        </div>
      )}

      {table.places.length > 0 && (
        <div className="text-body-medium text-on-surface-variant">
          <span className="text-label-small text-on-surface-variant">
            {DEBUG_TABLE_SCOPE_LABELS.places}{' '}
          </span>
          <span>{table.places.map(formatPlaceRef).join(', ')}</span>
        </div>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1">
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.observations}
          value={table.rowCount}
        />
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.coverage}
          value={coverage}
        />
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.unit}
          value={table.unit ?? undefined}
        />
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.scalingFactor}
          value={table.scalingFactor ?? undefined}
        />
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.measurementMethod}
          value={table.measurementMethod ?? undefined}
        />
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.observationPeriod}
          value={table.observationPeriod ?? undefined}
        />
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.facet}
          value={table.facetId ?? undefined}
        />
        <DebugDetail
          label={DEBUG_FACET_DETAIL_LABELS.license}
          value={table.source?.license ?? undefined}
        />
      </div>

      <div className="flex flex-col gap-1 text-body-medium text-on-surface-variant">
        <div>
          <span className="font-medium text-on-surface">{sourceName}</span>
          {showDataset && <span> · {table.source?.dataset}</span>}
          {showProvider && <span> · {table.source?.provider}</span>}
        </div>
        {table.source?.url ? (
          <Link
            href={table.source.url}
            title={table.source.url}
            className="min-h-11 inline-flex items-center max-w-full text-body-medium text-theme-primary truncate"
          >
            {table.source.url}
          </Link>
        ) : null}
      </div>
    </li>
  );
};

/**
 * Renders cached observation tables from authoritative server debug metrics.
 */
export const DataTab = ({ serverReport }: DataTabProps) => {
  if (serverReport === null) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.noServerReport}
      </p>
    );
  }

  if (serverReport.tables.length === 0) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.dataTables}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 text-on-surface">
      <DebugSection
        label={formatCachedTablesHeading(serverReport.tables.length)}
      >
        <ol className="list-none flex flex-col gap-3">
          {serverReport.tables.map((table) => (
            <CachedTableCard key={table.tableId} table={table} />
          ))}
        </ol>
      </DebugSection>
    </div>
  );
};
