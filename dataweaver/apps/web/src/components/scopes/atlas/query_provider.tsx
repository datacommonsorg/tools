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

import type {
  CardEntry,
  CombineStreamRequest,
  FollowUpContext,
  StreamEvent,
} from '~/server/types';
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

const COMBINE_KEYWORDS =
  /\b(combine|merge|put together|into one|single chart|one chart|unified chart|together in one)\b/i;

/** Detect whether the prompt intends to combine selected charts. */
const isCombineIntent = (prompt: string): boolean =>
  COMBINE_KEYWORDS.test(prompt);

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
      nodeSetComparison,
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
        ];

        // Only register a per-place notes card when notesHtml is present.
        // Multi-place queries omit notesHtml — a single comparison card is
        // registered via the comparisonResult event instead.
        if (result.notesHtml) {
          resultEntries.push({
            shapeId: `shape:${active.nodeId}__${entityDcid}__notes`,
            historyNodeId: active.nodeId,
            type: 'notes',
            placeDcid: entityDcid,
          });
        }

        // Register a per-place chart card only for single-place queries.
        // Multi-place queries get a combined comparison chart instead.
        const node = store.getState().nodes[active.nodeId];
        const isMultiPlace = (node?.parsedQuery?.places.length ?? 0) > 1;

        if (!isMultiPlace) {
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
        }

        cardRegisterBatch(resultEntries);
        active.cardIds.push(...resultEntries.map((e) => e.shapeId));

        break;
      }

      case STREAM_EVENT.comparisonResult: {
        const { result } = event;

        // Store the comparison on the history node.
        nodeSetComparison(active.nodeId, result);

        // Register a single comparison notes card.
        const comparisonEntries: CardEntry[] = [
          {
            shapeId: `shape:${active.nodeId}__comparison__notes`,
            historyNodeId: active.nodeId,
            type: 'notes',
            placeDcid: '__comparison',
          },
        ];

        // Register one comparison chart card per variable with chart metadata.
        if (result.charts) {
          for (const chart of result.charts) {
            comparisonEntries.push({
              shapeId: `shape:${active.nodeId}__comparison__chart__${chart.variableDcid}`,
              historyNodeId: active.nodeId,
              type: 'chart',
              placeDcid: '__comparison',
              variableDcid: chart.variableDcid,
            });
          }
        }

        cardRegisterBatch(comparisonEntries);
        active.cardIds.push(...comparisonEntries.map((e) => e.shapeId));

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
          getResultsForSelectedCards,
          nodeAddResult,
        } = store.getState();

        querySetProcessing(true);
        querySetStatus(STATUS.starting);

        // Derive context from selected shapes
        const selectedShapeIds = editor ? editor.getSelectedShapeIds() : [];
        const parentNodeId = getContextNodeId(selectedShapeIds);

        // ─── Combine flow ───────────────────────────────────────────────
        // When 2+ chart cards are selected and the prompt suggests combining,
        // skip the full query pipeline and run only the comparison step.
        const selectedResults = getResultsForSelectedCards(selectedShapeIds);
        if (selectedResults.length >= 2 && isCombineIntent(prompt)) {
          const nodeId = queryStart(prompt, null, parentNodeId);

          // Pre-populate the node with per-place results so that
          // deriveComparisonChartContent can build chart series.
          for (const result of selectedResults) {
            const entityDcid = result.entities[0]?.dcid;
            if (entityDcid) {
              nodeAddResult(nodeId, entityDcid, result);
            }
          }

          activeQueryRef.current = { nodeId, cardIds: [] };

          const combineRequest: CombineStreamRequest = {
            query: prompt,
            results: selectedResults,
          };
          startStream(combineRequest, '/api/combine');
          return;
        }

        // ─── Standard query flow ────────────────────────────────────────
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
