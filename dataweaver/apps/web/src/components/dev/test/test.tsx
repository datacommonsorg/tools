'use client';

import { nanoid } from 'nanoid/non-secure';
import { useCallback, useEffect, useRef } from 'react';
import { useAtlas } from '~/components/scopes/atlas/use_atlas';
import { useStreamingQuery } from '~/hooks/use-streaming-query';
import type {
  ChartMetadata,
  ChartSpec,
  QueryAnalysis,
  StreamEvent,
} from '~/server/types';
import { useDataWeaverStore } from '~/store';
import { TestInput } from './test-input';

export const Test = () => {
  const atlas = useAtlas();
  const store = useDataWeaverStore.getState();

  // Mutable refs for stream event handling (avoids stale closures)
  const nodeIdRef = useRef<string | null>(null);
  const currentChartSpecsRef = useRef<ChartSpec[]>([]);
  const currentMetadataMapRef = useRef(new Map<string, ChartMetadata>());
  const placeCardMapRef = useRef(new Map<string, string>());
  const parentNodeIdRef = useRef<string | null>(null);
  const queryTextRef = useRef<string>('');

  const { cards } = store;

  useEffect(() => {
    if (cards) {
      const cardIds = Object.keys(cards);

      cardIds.forEach((cardId) => {
        const card = cards[cardId];
        if (!card) return;

        console.log('Adding card to atlas:', card);
        atlas.add({
          id: cardId,
          variant: 'text',
          title: card.title,
          body: card.variableDcids?.join(', '),
          isLoading: true,
        });
      });
    }
  }, [atlas, cards]);

  // --- Get atlas context for AI queries (from store cards) ---
  const getAtlasContext = useCallback((): string => {
    const storeCards = store.cards;
    const variables = new Set<string>();
    const entities = new Set<string>();

    for (const card of Object.values(storeCards)) {
      card.variableDcids.forEach((v) => {
        variables.add(v);
      });
      card.entityDcids.forEach((e) => {
        entities.add(e);
      });
    }

    if (variables.size === 0 && entities.size === 0) return '';
    const parts: string[] = [];
    if (entities.size > 0)
      parts.push(`Places: ${Array.from(entities).join(', ')}`);
    if (variables.size > 0)
      parts.push(`Variables: ${Array.from(variables).join(', ')}`);
    return parts.join('. ');
  }, [store.cards]);

  // --- Currently gets all entity DCIDs from store ---
  // TODO: return selected entities once this is integrated with tldraw
  const getSelectedEntities = useCallback((): string[] => {
    const storeCards = store.cards;
    const entities = new Set<string>();
    for (const card of Object.values(storeCards)) {
      card.entityDcids.forEach((e) => {
        entities.add(e);
      });
    }
    return Array.from(entities);
  }, [store.cards]);

  const handleStreamEvent = useCallback(
    (event: StreamEvent) => {
      const setCurrentStatus = store.setCurrentStatus;

      console.log('Event type:', event.type);

      switch (event.type) {
        case 'status':
          console.log('Stream status:', event.message);
          setCurrentStatus(event.message);
          break;

        case 'analysis': {
          const analysis: QueryAnalysis = event.data;
          nodeIdRef.current = store.startQuery(
            queryTextRef.current,
            analysis,
            parentNodeIdRef.current,
          );

          // Create placeholder cards immediately so they render with titles
          placeCardMapRef.current.clear();
          for (const [place, title] of Object.entries(analysis.titles)) {
            const cardId = nanoid();
            placeCardMapRef.current.set(place, cardId);
            store.registerCard({
              shapeId: cardId,
              historyNodeId: nodeIdRef.current,
              type: 'loading',
              variableDcids: [],
              entityDcids: [],
              title,
            });
          }
          break;
        }

        case 'chart_spec': {
          const place = event.place;
          currentChartSpecsRef.current = event.specs;
          currentMetadataMapRef.current.clear();

          const cardId = placeCardMapRef.current.get(place);
          if (cardId) {
            const allVarDcids = event.specs.flatMap((s) =>
              s.variables.map((v) => v.dcid),
            );
            const allEntityDcids = event.specs.flatMap((s) =>
              s.entities.map((e) => e.dcid),
            );
            store.updateCard(cardId, {
              type: 'chart_spec',
              variableDcids: allVarDcids,
              entityDcids: allEntityDcids.length > 0 ? allEntityDcids : [place],
            });
          }
          break;
        }

        case 'metadata': {
          currentMetadataMapRef.current.set(
            event.data.variableDcid,
            event.data,
          );
          break;
        }

        case 'complete': {
          if (nodeIdRef.current) {
            const allCards = store.cards;
            const nodecardIds = Object.values(allCards)
              .filter((t) => t.historyNodeId === nodeIdRef.current)
              .map((t) => t.shapeId);
            store.completeQuery(nodeIdRef.current, nodecardIds);
          }
          store.setIsProcessing(false);
          store.setCurrentStatus('');
          break;
        }

        case 'error':
          store.setIsProcessing(false);
          store.setCurrentStatus('');
          break;
      }
    },
    [
      store.completeQuery,
      store.registerCard,
      store.updateCard,
      store.setIsProcessing,
      store.setCurrentStatus,
      store.startQuery,
      store.cards,
    ],
  );

  const { status, start } = useStreamingQuery(handleStreamEvent);

  const onSubmit = (input: string) => {
    const parentNodeId = store.getContextNodeId([]);
    parentNodeIdRef.current = parentNodeId;
    queryTextRef.current = input;

    const ancestorChain = store.getAncestorChain(parentNodeId).map((n) => ({
      query: n.query,
      topic: n.analysis.topic,
      places: n.analysis.places,
    }));

    start({
      query: input,
      atlasContext: getAtlasContext(),
      ancestorChain,
      selectedEntityDcids: getSelectedEntities(),
    });
  };

  return (
    <TestInput onSubmit={onSubmit} />
    // <div className={s.test}>
    //   <TestOutput status={status} />
    //   <TestInput onSubmit={onSubmit} />
    // </div>
  );
};
