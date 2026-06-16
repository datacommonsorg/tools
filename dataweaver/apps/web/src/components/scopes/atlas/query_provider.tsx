'use client';

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
} from 'react';
import type { TLShapeId } from 'tldraw';
import {
  type AtlasContextProps,
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
  placeholderShapeId: TLShapeId;
  placeholderUpdate: (props: Record<string, unknown>) => void;
  placeholderRemove: () => void;
  cardIds: string[];
  isFirstResult: boolean;
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
});

/** Build a text body from a query result's summary + insight. */
const buildBody = (result: QueryResult): string =>
  [result.summary, result.insight].filter(Boolean).join('\n\n');

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
      updateCard,
      registerCard,
      completeQuery,
      failQuery,
      setIsProcessing,
      unregisterCard,
    } = store.getState();

    switch (event.type) {
      case STREAM_EVENT.status:
        setCurrentStatus(event.message);
        break;

      case STREAM_EVENT.parsedQuery:
        setParsedQuery(active.nodeId, event.data);
        break;

      case STREAM_EVENT.queryResult: {
        const { result } = event;

        if (active.isFirstResult) {
          // First result — update the placeholder card in place
          active.isFirstResult = false;
          active.placeholderUpdate({
            title: result.title,
            body: buildBody(result),
            isLoading: false,
            followUp: result.followUps?.[0],
          });
          active.cardIds.push(String(active.placeholderShapeId));
          updateCard(String(active.placeholderShapeId), {
            type: 'query_result',
            variableDcids: result.variables.map((v) => v.dcid),
            entityDcids: result.entities.map((e) => e.dcid),
            title: result.title,
          });
        } else {
          // Subsequent results — create additional cards
          const handle = atlasRef.current.add({
            variant: 'text',
            title: result.title,
            body: buildBody(result),
            isLoading: false,
            followUp: result.followUps?.[0],
          });
          const entry = toCardEntry(String(handle.id), active.nodeId, result);
          registerCard(entry);
          active.cardIds.push(String(handle.id));
        }
        break;
      }

      case STREAM_EVENT.complete:
        completeQuery(active.nodeId, active.cardIds);
        setIsProcessing(false);
        setCurrentStatus('');
        activeQueryRef.current = null;
        break;

      case STREAM_EVENT.error:
        failQuery(active.nodeId);
        setIsProcessing(false);
        setCurrentStatus('');
        // Remove the placeholder card on error
        active.placeholderRemove();
        unregisterCard(String(active.placeholderShapeId));
        activeQueryRef.current = null;
        break;
    }
  }, []);

  const { start: startStream } = useStreamingQuery(handleStreamEvent);

  const providerValue = useMemo<QueryActionsContextProps>(
    () => ({
      runPrompt: (prompt: string) => {
        const {
          startQuery,
          registerCard,
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

        // Create placeholder card on atlas
        const handle = atlas.add({
          variant: 'text',
          title: prompt,
          isLoading: true,
        });

        // Register placeholder in store
        registerCard({
          shapeId: String(handle.id),
          historyNodeId: nodeId,
          type: 'loading',
          variableDcids: [],
          entityDcids: [],
          title: prompt,
        });

        // Store active query state for the stream handler
        activeQueryRef.current = {
          nodeId,
          placeholderShapeId: handle.id,
          placeholderUpdate: handle.update,
          placeholderRemove: handle.remove,
          cardIds: [],
          isFirstResult: true,
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
    [atlas, startStream],
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
