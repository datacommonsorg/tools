'use client';

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
} from 'react';
import { useAtlas } from '~/components/scopes/atlas/atlas_provider';
import { useStreamingQuery } from '~/components/scopes/atlas/hooks/use_streaming_query';
import type { StreamEvent } from '~/server/types';
import { STREAM_EVENT } from '~/server/types';
import { useDataWeaverStore } from '~/store';
import { useStoreShapeSync } from './sync_store';

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
}

export const QueryProvider = ({ children }: QueryProviderProps) => {
  const atlas = useAtlas();
  const activeQueryRef = useRef<ActiveQuery | null>(null);

  // Mount the store→shape sync layer.
  useStoreShapeSync(atlas);

  const store = useDataWeaverStore;

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    const active = activeQueryRef.current;
    if (!active) return;

    const {
      setParsedQuery,
      setCurrentStatus,
      addResult,
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

        // Register loading placeholder cards for each place.
        for (const place of event.data.places) {
          const shapeId = `shape:${active.nodeId}__${place}__loading`;
          registerCard(shapeId, active.nodeId, 'loading', place);
          active.cardIds.push(shapeId);
        }
        break;

      case STREAM_EVENT.queryResult: {
        const { result, place } = event;
        const entityDcid = result.entities[0]?.dcid ?? place;

        // Write the query result data to the history node.
        addResult(active.nodeId, entityDcid, result);

        // Remove the loading placeholder for this place and replace with real cards.
        const loadingId = `shape:${active.nodeId}__${place}__loading`;
        const { unregisterCard } = store.getState();
        unregisterCard(loadingId);
        active.cardIds = active.cardIds.filter((id) => id !== loadingId);

        // Register table card.
        const tableId = `shape:${active.nodeId}__${entityDcid}__table`;
        registerCard(tableId, active.nodeId, 'table', entityDcid);
        active.cardIds.push(tableId);

        // Register notes card.
        const notesId = `shape:${active.nodeId}__${entityDcid}__notes`;
        registerCard(notesId, active.nodeId, 'notes', entityDcid);
        active.cardIds.push(notesId);

        // Register chart card (only if data exists).
        const firstMeta = result.metadata[0];
        const firstFacet = firstMeta?.facets[0];
        if (firstFacet && firstFacet.observations.length > 0) {
          const chartId = `shape:${active.nodeId}__${entityDcid}__chart`;
          registerCard(chartId, active.nodeId, 'chart', entityDcid);
          active.cardIds.push(chartId);
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
          getSelectedEntityDcids,
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

        // Derive selected entity dcids from selected cards via store
        const selectedEntityDcids = getSelectedEntityDcids(selectedShapeIds);

        // Create history node in store
        const nodeId = startQuery(prompt, null, parentNodeId);

        // Store active query state for the stream handler
        activeQueryRef.current = {
          nodeId,
          cardIds: [],
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
