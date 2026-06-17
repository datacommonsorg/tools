'use client';

import { marked } from 'marked';
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
} from 'react';
import {
  type AtlasContextProps,
  type CardHandle,
  useAtlas,
} from '~/components/scopes/atlas/atlas_provider';
import { useStreamingQuery } from '~/components/scopes/atlas/hooks/use_streaming_query';
import type { CardEntry, QueryResult, StreamEvent } from '~/server/types';
import { STREAM_EVENT } from '~/server/types';
import { useDataWeaverStore } from '~/store';

export interface Status {
  promptValue: string;
  indicatorMessage: string;
}

interface QueryActionsContextProps {
  /** Run a query for the given prompt, streaming results onto the canvas. */
  runPrompt(prompt: string): void;
  /** Abort the in-flight query, remove its cards, and clean up the store. */
  cancelQuery(): void;
}

const QueryActionsContext = createContext<QueryActionsContextProps | null>(
  null,
);

interface QueryProviderProps {
  children: ReactNode;
}

/** Mutable state for an in-flight query, held by ref so the stream callback
 *  always reads fresh values without re-creating the closure. */
interface ActiveQuery {
  nodeId: string;
  cardIds: string[];
  removeCards: Array<() => void>;
  placeholderCards: Map<string, CardHandle<'table'>>;
}

/** Map a QueryResult into card entry fields for the store. */
const toCardEntry = (
  shapeId: string,
  historyNodeId: string,
  result: QueryResult,
): CardEntry => ({
  shapeId,
  historyNodeId,
  type: 'query_result',
  variableDcids: result.variables.map((v) => v.dcid),
  entityDcids: result.entities.map((e) => e.dcid),
  title: result.title,
  variables: result.variables,
  metadata: result.metadata,
  introduction: result.introduction,
  coverage: result.coverage,
  insights: result.insights,
  followUps: result.followUps,
});

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

export const QueryProvider = ({ children }: QueryProviderProps) => {
  const atlas = useAtlas();
  const activeQueryRef = useRef<ActiveQuery | null>(null);
  const atlasRef = useRef<AtlasContextProps>(atlas);
  atlasRef.current = atlas;

  const store = useDataWeaverStore;

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    const active = activeQueryRef.current;
    if (!active) return;

    const {
      setParsedQuery,
      setCurrentStatus,
      registerCard,
      completeQuery,
      failQuery,
      setIsProcessing,
    } = store.getState();

    switch (event.type) {
      case STREAM_EVENT.status:
        setCurrentStatus(event.message);
        break;

      case STREAM_EVENT.parsedQuery:
        setParsedQuery(active.nodeId, event.data);

        // Create loading placeholder cards for each place with the title.
        for (const place of event.data.places) {
          const title = event.data.titles[place] || place;
          const card = atlasRef.current.add({
            variant: 'table',
            title,
            isLoading: true,
          });
          active.placeholderCards.set(place, card);
          active.removeCards.push(() => card.remove());
        }
        break;

      case STREAM_EVENT.queryResult: {
        const { result, place } = event;

        // 1. Variables table card (table variant with HTML table)
        const existingCard = active.placeholderCards.get(place);
        let tableCardId: string;

        if (existingCard) {
          // Update the loading placeholder with real data.
          existingCard.update({
            title: result.title,
            body: buildTableHtml(result),
            isLoading: false,
          });
          tableCardId = String(existingCard.id);
          active.placeholderCards.delete(place);
        } else {
          // Fallback: no placeholder exists, create fresh.
          const tableCard = atlasRef.current.add({
            variant: 'table',
            title: result.title,
            body: buildTableHtml(result),
            isLoading: false,
          });
          tableCardId = String(tableCard.id);
          active.removeCards.push(() => tableCard.remove());
        }

        const tableEntry = toCardEntry(tableCardId, active.nodeId, result);
        registerCard(tableEntry);
        active.cardIds.push(tableCardId);

        // 2. Notes card (text variant with About this data + Relevant insights)
        const notesCard = atlasRef.current.add({
          variant: 'text',
          title: `${result.title} • Notes`,
          body: buildNotesHtml(result),
          isLoading: false,
          followUp: result.followUps?.[0],
        });
        const notesEntry = toCardEntry(
          String(notesCard.id),
          active.nodeId,
          result,
        );
        registerCard(notesEntry);
        active.cardIds.push(String(notesCard.id));
        active.removeCards.push(() => notesCard.remove());

        // 3. Chart card (observations from first variable's facets)
        const firstMeta = result.metadata[0];
        const allFacets = firstMeta?.facets;
        const firstFacet = allFacets?.[0];

        if (allFacets && firstFacet && firstFacet.observations.length > 0) {
          const chartCard = atlasRef.current.add({
            variant: 'chart',
            title: result.variables[0]?.name ?? result.title,
            description: firstFacet.source,
            data: firstFacet.observations,
            facets: allFacets,
            isLoading: false,
          });
          const chartEntry = toCardEntry(
            String(chartCard.id),
            active.nodeId,
            result,
          );
          registerCard(chartEntry);
          active.cardIds.push(String(chartCard.id));
          active.removeCards.push(() => chartCard.remove());
        }

        break;
      }

      case STREAM_EVENT.complete:
        completeQuery(active.nodeId, active.cardIds);
        setIsProcessing(false);
        setCurrentStatus(event.message);
        activeQueryRef.current = null;
        break;

      case STREAM_EVENT.error:
        failQuery(active.nodeId);
        setIsProcessing(false);
        setCurrentStatus('');
        activeQueryRef.current = null;
        break;
    }
  }, []);

  const { start: startStream, abort: abortStream } =
    useStreamingQuery(handleStreamEvent);

  const providerValue = useMemo<QueryActionsContextProps>(
    () => ({
      cancelQuery: () => {
        const active = activeQueryRef.current;
        if (!active) return;

        abortStream();

        for (const remove of active.removeCards) {
          remove();
        }

        store.getState().cancelQuery(active.nodeId);
        activeQueryRef.current = null;
      },
      runPrompt: (prompt: string) => {
        const {
          startQuery,
          setIsProcessing,
          setCurrentStatus,
          getAncestorChain,
          getContextNodeId,
          cards,
        } = store.getState();

        setIsProcessing(true);
        setCurrentStatus('Starting query...');

        // Derive context from selected shapes
        const selectedShapeIds = atlas.getSelectedShapeIds();
        const parentNodeId = getContextNodeId(selectedShapeIds);
        const ancestorChain = getAncestorChain(parentNodeId).map((node) => ({
          query: node.query,
          topic: node.parsedQuery?.topic ?? '',
          places: node.parsedQuery?.places ?? [],
        }));

        // Derive selected entity dcids from selected cards
        const selectedEntityDcids = selectedShapeIds.flatMap(
          (id) => cards[id]?.entityDcids ?? [],
        );

        // Create history node in store
        const nodeId = startQuery(prompt, null, parentNodeId);

        // Store active query state for the stream handler
        activeQueryRef.current = {
          nodeId,
          cardIds: [],
          removeCards: [],
          placeholderCards: new Map(),
        };

        // Build atlas context description for the API
        const atlasContext =
          ancestorChain.length > 0
            ? `Previous queries: ${ancestorChain.map((n) => n.query).join(' → ')}`
            : '';

        // Start the SSE stream
        startStream({
          query: prompt,
          atlasContext,
          ancestorChain,
          selectedEntityDcids,
        });
      },
    }),
    [atlas, startStream, abortStream],
  );

  return (
    <QueryActionsContext.Provider value={providerValue}>
      {children}
    </QueryActionsContext.Provider>
  );
};

/** Read the query actions — must be used inside `<QueryProvider>`. */
export const useQueryActions = (): QueryActionsContextProps => {
  const context = useContext(QueryActionsContext);
  if (!context) {
    throw new Error("'useQueryActions' must be used within 'QueryProvider'.");
  }

  return context;
};
