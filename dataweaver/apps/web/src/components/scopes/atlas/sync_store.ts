'use client';

import { useEffect, useRef } from 'react';
import type { ChartSeries } from '~/components/elements/card/chart/chart';
import {
  formatChartCardTitle,
  formatNotesCardTitle,
  formatTableCardTitle,
  resolvePlaceName,
} from '~/functions/format_card_title';
import { resolveResultForPlace } from '~/functions/scope_key';
import type {
  CardEntry,
  CardType,
  ChartStyle,
  ComparisonResult,
  QueryResult,
} from '~/server/types';
import { useAtlasStore } from '~/store';
import { type CardHandle, useAtlas } from './atlas_provider';
import type { AtlasContent, CardVariant } from './helpers';

// --- Derivation functions ---
// These convert raw QueryResult data from the store into AtlasContent for shapes.

/** Derive AtlasContent for a loading placeholder card. */
export const deriveLoadingContent = (title: string): AtlasContent => ({
  variant: 'table',
  title,
  isLoading: true,
});

/** Derive AtlasContent for a table card from a QueryResult. */
export const deriveTableContent = (result: QueryResult): AtlasContent => {
  const placeName = resolvePlaceName(result);
  const title =
    result.title || formatTableCardTitle(placeName, result.isChildQuery);
  return {
    variant: 'table',
    title,
    body: result.tableHtml ?? '',
    isLoading: false,
  };
};

/** Derive AtlasContent for a notes card from a QueryResult. */
export const deriveNotesContent = (result: QueryResult): AtlasContent => {
  const placeName = resolvePlaceName(result);
  const title = formatNotesCardTitle(placeName);

  return {
    variant: 'text',
    title,
    body: result.notesHtml ?? '',
    isLoading: false,
    relatedQueries: result.relatedQueries,
  };
};

/** Derive AtlasContent for a cross-place comparison card. */
export const deriveComparisonContent = (
  comparison: ComparisonResult,
): AtlasContent => ({
  variant: 'text',
  title: comparison.title,
  body: comparison.notesHtml ?? '',
  isLoading: false,
  relatedQueries: comparison.relatedQueries,
});

/** Derive AtlasContent for a comparison chart card (multi-series, one variable across places). */
export const deriveComparisonChartContent = (
  comparison: ComparisonResult,
  variableDcid: string,
  allResults: Record<string, QueryResult>,
): AtlasContent | null => {
  const chartMeta = comparison.charts?.find(
    (c) => c.variableDcid === variableDcid,
  );
  if (!chartMeta) return null;

  const series: ChartSeries[] = [];

  const resultEntries = Object.values(allResults);
  const allPlaces = new Set(
    resultEntries
      .map(
        (result) =>
          result.placeDcid ||
          result.parentPlaceDcid ||
          result.entities[0]?.dcid,
      )
      .filter(Boolean),
  );
  const isSamePlace = allPlaces.size === 1;

  if (isSamePlace) {
    // Same-place, different-variable: overlay ALL variables in the merged
    // result as separate series. The chart represents a variable comparison
    // within one place, so we always show every time series regardless of
    // which variableDcid the chart metadata references.
    const result = resultEntries[0];
    if (!result) return null;

    for (const ts of result.timeSeries) {
      const plottableFacet = ts.facets.find((f) => f.observations.length > 0);
      const observations = plottableFacet?.observations;
      if (!observations || observations.length === 0) continue;

      const variable = result.variables.find(
        (entry) => entry.dcid === ts.variableDcid,
      );
      const label = variable?.name ?? ts.variableDcid;

      series.push({
        key: ts.variableDcid,
        label,
        data: observations,
        unit: plottableFacet?.unit,
        facets: ts.facets,
      });
    }
  } else {
    // Different-place: build one series per place (original behavior).
    for (const result of resultEntries) {
      const ts = result.timeSeries.find((t) => t.variableDcid === variableDcid);
      if (!ts) continue;
      const plottableFacet = ts.facets.find((f) => f.observations.length > 0);
      const observations = plottableFacet?.observations;
      if (!observations || observations.length === 0) continue;

      const placeDcid =
        result.placeDcid ||
        result.parentPlaceDcid ||
        result.entities[0]?.dcid ||
        result.id;
      const placeName = resolvePlaceName(result);

      series.push({
        key: placeDcid,
        label: placeName,
        data: observations,
        unit: plottableFacet?.unit,
        facets: ts.facets,
      });
    }
  }

  if (series.length === 0) return null;

  return {
    variant: 'chart',
    title: chartMeta.title,
    description: chartMeta.description,
    series,
    isLoading: false,
  };
};

/**
 * Derive AtlasContent for a chart card from a QueryResult.
 * Handles both multi-entity (regional comparisons/choropleths) and single-entity views,
 * optionally targeting a specific variable and/or specific child place.
 */
export const deriveChartContent = (
  result: QueryResult,
  variableDcid?: string,
  childPlaceDcid?: string,
): AtlasContent | null => {
  const plottableVar = result.timeSeries.find(
    (ts) =>
      (!childPlaceDcid || ts.entityDcid === childPlaceDcid) &&
      ts.facets.some((f) => f.observations.length > 0),
  )?.variableDcid;
  const effectiveVar =
    variableDcid || plottableVar || result.variables[0]?.dcid;
  if (!effectiveVar) return null;

  const isSpecificChildPlace = Boolean(childPlaceDcid);
  const placeName = resolvePlaceName(result);

  if (result.entities.length > 1 && !isSpecificChildPlace) {
    const series: ChartSeries[] = [];

    for (const entity of result.entities) {
      const ts = result.timeSeries.find(
        (t) => t.variableDcid === effectiveVar && t.entityDcid === entity.dcid,
      );
      const plottableFacet = ts?.facets.find((f) => f.observations.length > 0);
      const observations = plottableFacet?.observations;
      if (!observations || observations.length === 0) continue;

      series.push({
        key: entity.dcid,
        label: entity.name || entity.dcid,
        data: observations,
        unit: plottableFacet?.unit,
        facets: ts?.facets,
      });
    }

    if (series.length === 0) return null;

    const variable = result.variables.find((v) => v.dcid === effectiveVar);
    const title = formatChartCardTitle(
      variable?.name,
      placeName,
      result.isChildQuery,
    );
    const parentPlaceDcid = result.parentPlaceDcid;

    return {
      variant: 'chart',
      title,
      description: variable?.rationale || undefined,
      series,
      parentPlaceDcid,
      isLoading: false,
    };
  }

  const timeSeries = result.timeSeries.find(
    (m) =>
      m.variableDcid === effectiveVar &&
      (!childPlaceDcid || m.entityDcid === childPlaceDcid),
  );
  const allFacets = timeSeries?.facets;
  const plottableFacet = allFacets?.find((f) => f.observations.length > 0);

  if (!allFacets || !plottableFacet) {
    return null;
  }

  const specificEntity = isSpecificChildPlace
    ? result.entities.find((e) => e.dcid === childPlaceDcid)
    : undefined;
  const targetPlaceName =
    specificEntity?.name ||
    timeSeries?.entityName ||
    childPlaceDcid ||
    placeName;
  const targetPlaceDcid =
    childPlaceDcid ||
    specificEntity?.dcid ||
    result.placeDcid ||
    result.entities[0]?.dcid ||
    'default';
  const variable = result.variables.find((v) => v.dcid === effectiveVar);
  const title = formatChartCardTitle(variable?.name, targetPlaceName, false);
  const parentPlaceDcid =
    result.isChildQuery && !isSpecificChildPlace
      ? result.parentPlaceDcid
      : undefined;

  return {
    variant: 'chart',
    title,
    description: variable?.rationale || plottableFacet.source || undefined,
    series: [
      {
        key: targetPlaceDcid,
        label: targetPlaceName,
        data: plottableFacet.observations,
        unit: plottableFacet.unit,
        facets: allFacets,
      },
    ],
    parentPlaceDcid,
    isLoading: false,
  };
};

/** Derive AtlasContent for a given card type and its associated query result. */
export const deriveContentForCard = (
  type: CardType,
  result: QueryResult | undefined,
  placeholderTitle?: string,
  variableDcid?: string,
  comparison?: ComparisonResult,
  allResults?: Record<string, QueryResult>,
  chartStyle?: ChartStyle,
  childPlaceDcid?: string,
): AtlasContent | null => {
  if (type === 'loading') {
    return deriveLoadingContent(placeholderTitle ?? '');
  }
  // Comparison cards read from the dedicated comparison field.
  if (comparison && type === 'notes') {
    return deriveComparisonContent(comparison);
  }
  if (comparison && type === 'chart' && variableDcid && allResults) {
    return finalizeChartContent(
      deriveComparisonChartContent(comparison, variableDcid, allResults),
      chartStyle,
    );
  }
  if (!result) return null;
  switch (type) {
    case 'table':
      return deriveTableContent(result);
    case 'notes':
      return deriveNotesContent(result);
    case 'chart': {
      const content = deriveChartContent(result, variableDcid, childPlaceDcid);
      return finalizeChartContent(content, chartStyle);
    }
  }
};

/** Sort series alphabetically by label using deterministic English locale to prevent SSR hydration mismatches. */
const sortSeries = (series: ChartSeries[]): ChartSeries[] =>
  series.sort((a, b) =>
    (a.label ?? '').localeCompare(b.label ?? '', 'en', {
      sensitivity: 'base',
      numeric: true,
    }),
  );

/** Finalize chart content: sort multi-series data alphabetically and apply chart style override. */
const finalizeChartContent = (
  content: AtlasContent | null,
  chartStyle?: ChartStyle,
): AtlasContent | null => {
  if (!content || content.variant !== 'chart') return content;
  if (content.series && content.series.length > 1) {
    sortSeries(content.series);
  }
  if (chartStyle) {
    return { ...content, chartStyle };
  }
  return content;
};

// --- Sync hook ---

/**
 * Hook that synchronizes the zustand store → tldraw shapes.
 * When cards are registered/unregistered in the store, this hook creates,
 * updates, or removes the corresponding tldraw shapes via the atlas API.
 */
export const useStoreShapeSync = () => {
  const { add } = useAtlas();

  const handlesRef = useRef<Map<string, CardHandle<CardVariant>>>(new Map());
  const prevCardsRef = useRef<Record<string, CardEntry>>({});

  useEffect(() => {
    const unsubscribe = useAtlasStore.subscribe(
      (state) => state.cards,
      (cards) => {
        const prevCards = prevCardsRef.current;

        const handles = handlesRef.current;
        const nodes = useAtlasStore.getState().nodes;

        // Detect new cards
        for (const [shapeId, card] of Object.entries(cards)) {
          if (prevCards[shapeId]) continue;

          const node = nodes[card.historyNodeId];
          const isComparison = card.placeDcid === '__comparison';
          const resultKey = card.parentPlaceDcid || card.placeDcid;
          const result = isComparison
            ? undefined
            : resolveResultForPlace(node?.results, resultKey);
          const comparison = isComparison ? node?.comparison : undefined;
          const title =
            node?.parsedQuery?.titles[card.placeDcid] || card.placeDcid;

          const content = deriveContentForCard(
            card.type,
            result,
            title,
            card.variableDcid,
            comparison,
            isComparison ? node?.results : undefined,
            card.chartStyle,
            card.parentPlaceDcid ? card.placeDcid : undefined,
          );
          if (!content) continue;

          const handle = add(content, shapeId);
          handles.set(shapeId, handle);
        }

        // Detect cards whose type changed (loading → real)
        for (const [shapeId, card] of Object.entries(cards)) {
          const prevCard = prevCards[shapeId];
          if (!prevCard || prevCard.type === card.type) continue;

          const node = nodes[card.historyNodeId];
          const isComparison = card.placeDcid === '__comparison';
          const resultKey = card.parentPlaceDcid || card.placeDcid;
          const result = isComparison
            ? undefined
            : resolveResultForPlace(node?.results, resultKey);
          const comparison = isComparison ? node?.comparison : undefined;
          const content = deriveContentForCard(
            card.type,
            result,
            undefined,
            card.variableDcid,
            comparison,
            isComparison ? node?.results : undefined,
            card.chartStyle,
            card.parentPlaceDcid ? card.placeDcid : undefined,
          );
          if (!content) continue;

          const handle = handles.get(shapeId);
          if (handle) {
            const { variant: _, ...updateProps } = content;
            handle.update(updateProps as Parameters<typeof handle.update>[0]);
          }
        }

        // Detect cards whose chartStyle changed
        for (const [shapeId, card] of Object.entries(cards)) {
          const prevCard = prevCards[shapeId];
          if (!prevCard || prevCard.chartStyle === card.chartStyle) continue;
          // Skip cards already handled by the type-change block above.
          if (prevCard.type !== card.type) continue;

          const handle = handles.get(shapeId);
          if (handle) {
            handle.update({ chartStyle: card.chartStyle } as Parameters<
              typeof handle.update
            >[0]);
          }
        }

        // Detect removed cards
        for (const shapeId of Object.keys(prevCards)) {
          if (cards[shapeId]) continue;
          const handle = handles.get(shapeId);
          if (handle) {
            handle.remove();
            handles.delete(shapeId);
          }
        }

        prevCardsRef.current = cards;
      },
    );

    return () => unsubscribe();
  }, [add]);

  return handlesRef;
};
