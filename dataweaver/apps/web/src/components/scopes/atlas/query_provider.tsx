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

import type { CardEntry, FollowUpContext, StreamEvent } from '~/server/types';
import { STATUS, STREAM_EVENT } from '~/server/types';
import { useAtlasStore } from '~/store';
import { useAtlas } from './atlas_provider';
import { useStoreShapeSync } from './sync_store';
import { useStreamingQuery } from './use_streaming_query';

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
  const { editor } = useAtlas();

  // Mount the store→shape sync layer
  useStoreShapeSync();

  const activeQueryRef = useRef<ActiveQuery | null>(null);

  const store = useAtlasStore;

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    const active = activeQueryRef.current;
    if (!active) return;

    const {
      nodeSetParsedQuery,
      querySetStatus,
      nodeAddResult,
      nodeSetFollowUp,
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
        break;
      }

      case STREAM_EVENT.queryResult: {
        const { result, place } = event;
        const entityDcid = result.entities[0]?.dcid ?? place;

        console.log('EVENT', event);
        // Write the query result data to the history node.
        nodeAddResult(active.nodeId, entityDcid, result);

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
        const remaining: string[] = [];
        for (const id of active.cardIds) {
          remaining.push(id);
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
        toast('Place skipped', event.reason);
        querySetStatus(event.reason);
        break;
      }

      case STREAM_EVENT.followUp: {
        nodeSetFollowUp(active.nodeId, event.data);
        break;
      }
    }
  }, []);

  const { start: startStream, abort: abortStream } =
    useStreamingQuery(handleStreamEvent);

  const providerValue = useMemo<QueryActionsContextProps>(
    () => ({
      runPrompt: (prompt: string) => {
        const {
          nodes,
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
        const selectedShapeIds = editor ? editor.getSelectedShapeIds() : [];
        const parentNodeId = getContextNodeId(selectedShapeIds);
        const ancestorChain = getAncestorChain(parentNodeId).map((node) => ({
          query: node.query,
          topic: node.parsedQuery?.topic ?? '',
          places: node.parsedQuery?.places ?? [],
        }));

        // If the parent node had a followUp, build structured context
        // instead of concatenating into the query string.
        let followUpContext: FollowUpContext | undefined;
        if (parentNodeId) {
          const parentNode = nodes[parentNodeId];
          const parentFollowUp = parentNode?.followUp;

          if (parentFollowUp && parentNode) {
            if (parentNode.followUpContext) {
              // Extend existing chain
              followUpContext = {
                originalQuery: parentNode.followUpContext.originalQuery,
                followUps: [
                  ...parentNode.followUpContext.followUps,
                  { question: parentFollowUp.question, answer: prompt },
                ],
              };
            } else {
              // Start a new chain
              followUpContext = {
                originalQuery: parentNode.query,
                followUps: [
                  { question: parentFollowUp.question, answer: prompt },
                ],
              };
            }
          }
        }

        // Derive selected entity dcids from selected cards via store
        const selectedEntityDcids = getSelectedEntityDcids(selectedShapeIds);

        // Create history node in store
        const nodeId = queryStart(prompt, null, parentNodeId, followUpContext);

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
          followUpContext,
        });
      },
      queryCancel: () => {
        const active = activeQueryRef.current;
        if (!active) return;

        abortStream();
        store.getState().queryCancel(active.nodeId);
        activeQueryRef.current = null;
      },
    }),
    [editor, startStream, abortStream],
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
