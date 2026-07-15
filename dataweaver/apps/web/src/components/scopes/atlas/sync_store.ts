'use client';

import { useEffect, useRef } from 'react';
import type {
  CardEntry,
  CardType,
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
export const deriveTableContent = (result: QueryResult): AtlasContent => ({
  variant: 'table',
  title: result.title,
  body: result.tableHtml ?? '',
  isLoading: false,
});

/** Derive AtlasContent for a notes card from a QueryResult. */
export const deriveNotesContent = (result: QueryResult): AtlasContent => ({
  variant: 'text',
  title: `${result.title} • Notes`,
  body: result.notesHtml ?? '',
  isLoading: false,
  relatedQueries: result.relatedQueries,
});

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

/** Derive AtlasContent for a chart card from a QueryResult (first variable's facets). */
export const deriveChartContent = (
  result: QueryResult,
): AtlasContent | null => {
  const firstTimeSeries = result.timeSeries[0];
  const allFacets = firstTimeSeries?.facets;
  const firstFacet = allFacets?.[0];

  if (!allFacets || !firstFacet || firstFacet.observations.length === 0) {
    return null;
  }

  const varName = result.variables[0]?.name;
  const placeName = result.entities[0]?.name;
  const title =
    varName && placeName ? `${varName} in ${placeName}` : result.title;

  return {
    variant: 'chart',
    title,
    description: result.variables[0]?.rationale ?? firstFacet.source,
    data: firstFacet.observations,
    facets: allFacets,
    isLoading: false,
  };
};

/** Derive AtlasContent for a chart card targeting a specific variable by DCID. */
export const deriveChartContentForVariable = (
  result: QueryResult,
  variableDcid: string,
  entityDcid?: string,
): AtlasContent | null => {
  const timeSeries = result.timeSeries.find(
    (m) =>
      m.variableDcid === variableDcid &&
      (!entityDcid || m.entityDcid === entityDcid),
  );
  const allFacets = timeSeries?.facets;
  const firstFacet = allFacets?.[0];

  if (!allFacets || !firstFacet || firstFacet.observations.length === 0) {
    return null;
  }

  const variable = result.variables.find((v) => v.dcid === variableDcid);
  const placeName = entityDcid
    ? result.entities.find((e) => e.dcid === entityDcid)?.name
    : result.entities[0]?.name;
  const varName = variable?.name;
  const title =
    varName && placeName ? `${varName} in ${placeName}` : result.title;

  return {
    variant: 'chart',
    title,
    description: variable?.rationale ?? firstFacet.source,
    data: firstFacet.observations,
    facets: allFacets,
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
): AtlasContent | null => {
  if (type === 'loading') {
    return deriveLoadingContent(placeholderTitle ?? '');
  }
  // Comparison cards read from the dedicated comparison field.
  if (comparison && type === 'notes') {
    return deriveComparisonContent(comparison);
  }
  if (!result) return null;
  switch (type) {
    case 'table':
      return deriveTableContent(result);
    case 'notes':
      return deriveNotesContent(result);
    case 'chart':
      return variableDcid
        ? deriveChartContentForVariable(result, variableDcid)
        : deriveChartContent(result);
  }
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
          const result = isComparison
            ? undefined
            : node?.results[card.placeDcid];
          const comparison = isComparison ? node?.comparison : undefined;
          const title =
            node?.parsedQuery?.titles[card.placeDcid] || card.placeDcid;

          const content = deriveContentForCard(
            card.type,
            result,
            title,
            card.variableDcid,
            comparison,
          );
          if (!content) continue;

          // Pass raw ID (strip "shape:" prefix) so tldraw shape ID matches store key.
          const rawId = shapeId.replace(/^shape:/, '');
          const handle = add(content, rawId);
          handles.set(shapeId, handle);
        }

        // Detect cards whose type changed (loading → real)
        for (const [shapeId, card] of Object.entries(cards)) {
          const prevCard = prevCards[shapeId];
          if (!prevCard || prevCard.type === card.type) continue;

          const node = nodes[card.historyNodeId];
          const isComparison = card.placeDcid === '__comparison';
          const result = isComparison
            ? undefined
            : node?.results[card.placeDcid];
          const comparison = isComparison ? node?.comparison : undefined;
          const content = deriveContentForCard(
            card.type,
            result,
            undefined,
            card.variableDcid,
            comparison,
          );
          if (!content) continue;

          const handle = handles.get(shapeId);
          if (handle) {
            const { variant: _, ...updateProps } = content;
            handle.update(updateProps as Parameters<typeof handle.update>[0]);
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
