'use client';

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
} from 'react';
import { toast } from '~/components/foundations/toaster/store';
import { useAtlas } from '~/components/scopes/atlas/atlas_provider';
import { useStreamingQuery } from '~/components/scopes/atlas/hooks/use_streaming_query';
import type { CardEntry, StreamEvent } from '~/server/types';
import { STATUS, STREAM_EVENT } from '~/server/types';
import { useAtlasStore } from '~/store';
import { useStoreShapeSync } from './sync_store';

export interface Status {
  promptValue: string;
  indicatorMessage: string;
}

interface QueryActionsContextProps {
  /** Run a query for the given prompt, streaming results onto the canvas. */
  runPrompt(prompt: string): void;
  /** Abort the in-flight query, remove its cards, and clean up the store. */
  queryCancel(): void;
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

  const store = useAtlasStore;

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    const active = activeQueryRef.current;
    if (!active) return;

    const {
      nodeSetParsedQuery,
      querySetStatus,
      nodeAddResult,
      cardRegisterBatch,
      queryComplete,
      queryFail,
      querySetProcessing,
    } = store.getState();

    switch (event.type) {
      case STREAM_EVENT.status:
        querySetStatus(event.message);
        break;

      case STREAM_EVENT.parsedQuery: {
        nodeSetParsedQuery(active.nodeId, event.data);

        // Register loading placeholder cards for each place.
        const loadingEntries = event.data.places.map((place) => ({
          shapeId: `shape:${active.nodeId}__${place}__loading`,
          historyNodeId: active.nodeId,
          type: 'loading' as const,
          placeDcid: place,
        }));
        cardRegisterBatch(loadingEntries);
        active.cardIds.push(...loadingEntries.map((e) => e.shapeId));
        break;
      }

      case STREAM_EVENT.queryResult: {
        const { result, place } = event;
        const entityDcid = result.entities[0]?.dcid ?? place;

        // Write the query result data to the history node.
        nodeAddResult(active.nodeId, entityDcid, result);

        // Remove the loading placeholder for this place.
        const loadingId = `shape:${active.nodeId}__${place}__loading`;
        const { cardUnregister } = store.getState();
        cardUnregister(loadingId);
        active.cardIds = active.cardIds.filter((id) => id !== loadingId);

        if (result.disambiguation) {
          // Handle disambiguation if present
          queryFail(active.nodeId);
          querySetProcessing(false);
          querySetStatus(STATUS.idle);
          break;
        }

        // Batch-register result cards.
        const resultEntries: CardEntry[] = [
          {
            shapeId: `shape:${active.nodeId}__${entityDcid}__table`,
            historyNodeId: active.nodeId,
            type: 'table',
            placeDcid: entityDcid,
          },
          {
            shapeId: `shape:${active.nodeId}__${entityDcid}__notes`,
            historyNodeId: active.nodeId,
            type: 'notes',
            placeDcid: entityDcid,
          },
        ];

        const firstTimeSeries = result.timeSeries[0];
        const firstFacet = firstTimeSeries?.facets[0];
        if (firstFacet && firstFacet.observations.length > 0) {
          resultEntries.push({
            shapeId: `shape:${active.nodeId}__${entityDcid}__chart`,
            historyNodeId: active.nodeId,
            type: 'chart',
            placeDcid: entityDcid,
          });
        }

        cardRegisterBatch(resultEntries);
        active.cardIds.push(...resultEntries.map((e) => e.shapeId));

        break;
      }

      case STREAM_EVENT.complete: {
        // Defensive cleanup: remove any orphan loading cards that were never
        // resolved (e.g. if a placeSkipped event was somehow missed).
        const { cardUnregister: unregisterOrphan, cards } = store.getState();
        const remaining: string[] = [];
        for (const id of active.cardIds) {
          const card = cards[id];
          if (card?.type === 'loading') {
            unregisterOrphan(id);
          } else {
            remaining.push(id);
          }
        }

        queryComplete(active.nodeId, remaining);
        querySetProcessing(false);
        querySetStatus(event.message);
        activeQueryRef.current = null;
        break;
      }

      case STREAM_EVENT.error: {
        toast('Query failed', event.message);
        queryFail(active.nodeId);
        querySetProcessing(false);
        querySetStatus(STATUS.idle);
        activeQueryRef.current = null;
        break;
      }

      case STREAM_EVENT.placeSkipped: {
        // Remove the loading placeholder for this skipped place.
        const loadingId = `shape:${active.nodeId}__${event.place}__loading`;
        const { cardUnregister: unregisterSkipped } = store.getState();
        unregisterSkipped(loadingId);
        active.cardIds = active.cardIds.filter((id) => id !== loadingId);
        toast('Place skipped', event.reason);
        querySetStatus(event.reason);
        break;
      }
    }
  }, []);

  const { start: startStream, abort: abortStream } =
    useStreamingQuery(handleStreamEvent);

  const providerValue = useMemo<QueryActionsContextProps>(
    () => ({
      queryCancel: () => {
        const active = activeQueryRef.current;
        if (!active) return;

        abortStream();
        store.getState().queryCancel(active.nodeId);
        activeQueryRef.current = null;
      },
      runPrompt: (prompt: string) => {
        const {
          queryStart,
          querySetProcessing,
          querySetStatus,
          getAncestorChain,
          getContextNodeId,
          getSelectedEntityDcids,
        } = store.getState();

        querySetProcessing(true);
        querySetStatus(STATUS.starting);

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
        const nodeId = queryStart(prompt, null, parentNodeId);

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
