'use client';

import { marked } from 'marked';
import { useEffect, useRef } from 'react';
import type { CardEntry, CardType, QueryResult } from '~/server/types';
import { useDataWeaverStore } from '~/store';
import type { AtlasContextProps, CardHandle } from './atlas_provider';
import type { AtlasContent, CardVariant } from './helpers';

// --- Derivation functions ---
// These convert raw QueryResult data from the store into AtlasContent for shapes.

/** Build the variables table as an HTML string from a query result. */
const buildTableHtml = (result: QueryResult): string => {
  const entityDcid = result.entities[0]?.dcid ?? '';
  const placeName = result.entities[0]?.name ?? '';
  const intro = result.introduction ?? '';

  let md = intro ? `${intro}\n\n` : '';
  md += '| Statistical variable | Facet(s) | Rationale |\n';
  md += '| --- | --- | --- |\n';

  for (const variable of result.variables) {
    const meta = result.metadata.find((m) => m.variableDcid === variable.dcid);
    const firstFacet = meta?.facets[0];
    const facetCell = firstFacet
      ? `${firstFacet.source}<br>${firstFacet.earliestDate} – ${firstFacet.latestDate}${firstFacet.unit ? ` · ${firstFacet.unit}` : ''}`
      : 'No data';

    const encodedVar = encodeURIComponent(variable.name);
    const encodedPlace = encodeURIComponent(placeName);
    const link = `[${variable.name}](#fetch=${variable.dcid}&place=${entityDcid}&varName=${encodedVar}&placeName=${encodedPlace})`;

    md += `| ${link} | ${facetCell} | ${variable.rationale ?? '—'} |\n`;
  }

  return marked.parse(md) as string;
};

/** Build the notes card HTML from a query result's introduction + insights. */
const buildNotesHtml = (result: QueryResult): string => {
  let md = '### About this data\n\n';
  if (result.coverage) {
    md += `${result.coverage}\n\n`;
  }
  if (result.introduction) {
    md += `${result.introduction}\n\n`;
  }

  if (result.insights && result.insights.length > 0) {
    md += '### Relevant insights\n\n';
    for (const insight of result.insights) {
      md += `- **${insight.title}**: ${insight.text}\n`;
    }
  }

  return marked.parse(md) as string;
};

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
  body: buildTableHtml(result),
  isLoading: false,
});

/** Derive AtlasContent for a notes card from a QueryResult. */
export const deriveNotesContent = (result: QueryResult): AtlasContent => ({
  variant: 'text',
  title: `${result.title} • Notes`,
  body: buildNotesHtml(result),
  isLoading: false,
  followUp: result.followUps?.[0],
});

/** Derive AtlasContent for a chart card from a QueryResult (first variable's facets). */
export const deriveChartContent = (
  result: QueryResult,
): AtlasContent | null => {
  const firstMeta = result.metadata[0];
  const allFacets = firstMeta?.facets;
  const firstFacet = allFacets?.[0];

  if (!allFacets || !firstFacet || firstFacet.observations.length === 0) {
    return null;
  }

  return {
    variant: 'chart',
    title: result.variables[0]?.name ?? result.title,
    description: firstFacet.source,
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
): AtlasContent | null => {
  if (type === 'loading') {
    return deriveLoadingContent(placeholderTitle ?? '');
  }
  if (!result) return null;
  switch (type) {
    case 'table':
      return deriveTableContent(result);
    case 'notes':
      return deriveNotesContent(result);
    case 'chart':
      return deriveChartContent(result);
  }
};

// --- Sync hook ---

/**
 * Hook that synchronizes the zustand store → tldraw shapes.
 * When cards are registered/unregistered in the store, this hook creates,
 * updates, or removes the corresponding tldraw shapes via the atlas API.
 */
export const useStoreShapeSync = (atlas: AtlasContextProps) => {
  const handlesRef = useRef<Map<string, CardHandle<CardVariant>>>(new Map());
  const prevCardsRef = useRef<Record<string, CardEntry>>({});

  useEffect(() => {
    const unsubscribe = useDataWeaverStore.subscribe((state) => {
      const cards = state.cards;
      const prevCards = prevCardsRef.current;

      // Skip if cards reference hasn't changed.
      if (cards === prevCards) return;

      const handles = handlesRef.current;
      const { nodes } = state;

      // Detect new cards
      for (const [shapeId, card] of Object.entries(cards)) {
        if (prevCards[shapeId]) continue;

        const node = nodes[card.historyNodeId];
        const result = node?.results[card.placeDcid];
        const title =
          node?.parsedQuery?.titles[card.placeDcid] || card.placeDcid;

        const content = deriveContentForCard(card.type, result, title);
        if (!content) continue;

        // Pass raw ID (strip "shape:" prefix) so tldraw shape ID matches store key.
        const rawId = shapeId.replace(/^shape:/, '');
        const handle = atlas.add(content, rawId);
        handles.set(shapeId, handle);
      }

      // Detect cards whose type changed (loading → real)
      for (const [shapeId, card] of Object.entries(cards)) {
        const prevCard = prevCards[shapeId];
        if (!prevCard || prevCard.type === card.type) continue;

        const node = nodes[card.historyNodeId];
        const result = node?.results[card.placeDcid];
        const content = deriveContentForCard(card.type, result);
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
    });

    return () => unsubscribe();
  }, [atlas]);

  return handlesRef;
};
