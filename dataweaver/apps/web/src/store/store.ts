import { nanoid } from 'nanoid';
import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type {
  CardEntry,
  CardType,
  HistoryNode,
  ParsedQuery,
  QueryResult,
} from '~/server/types';

const MAX_ANCESTOR_CHAIN = 10;

export interface DataWeaverStore {
  // --- History ---
  nodes: Record<string, HistoryNode>;
  latestNodeId: string | null;

  // --- Card registry ---
  cards: Record<string, CardEntry>;

  // --- UI state ---
  isProcessing: boolean;
  currentStatus: string;

  // --- Actions ---
  startQuery: (
    query: string,
    parsedQuery: ParsedQuery | null,
    parentNodeId: string | null,
  ) => string;
  setParsedQuery: (nodeId: string, parsedQuery: ParsedQuery) => void;
  addResult: (nodeId: string, placeDcid: string, result: QueryResult) => void;
  completeQuery: (nodeId: string, cardIds: string[]) => void;
  failQuery: (nodeId: string) => void;
  registerCard: (
    shapeId: string,
    historyNodeId: string,
    type: CardType,
    placeDcid: string,
    variableDcid?: string,
  ) => void;
  unregisterCard: (shapeId: string) => void;
  cancelQuery: (nodeId: string) => void;
  setIsProcessing: (val: boolean) => void;
  setCurrentStatus: (val: string) => void;

  // --- Selectors ---
  getAncestorChain: (nodeId: string | null) => HistoryNode[];
  getContextNodeId: (selectedShapeIds: string[]) => string | null;
  getSelectedEntityDcids: (selectedShapeIds: string[]) => string[];
}

export const useDataWeaverStore = create<DataWeaverStore>()(
  devtools(
    (set, get) => ({
      nodes: {},
      latestNodeId: null,
      cards: {},
      isProcessing: false,
      currentStatus: '',

      startQuery: (query, parsedQuery, parentNodeId) => {
        const id = nanoid();
        const node: HistoryNode = {
          id,
          parentId: parentNodeId,
          query,
          parsedQuery,
          results: {},
          cardIds: [],
          timestamp: Date.now(),
          status: 'pending',
        };
        set(
          (state) => ({
            nodes: { ...state.nodes, [id]: node },
            latestNodeId: id,
          }),
          undefined,
          'startQuery',
        );
        return id;
      },

      setParsedQuery: (nodeId, parsedQuery) => {
        set(
          (state) => {
            const node = state.nodes[nodeId];
            if (!node) return state;
            return {
              nodes: {
                ...state.nodes,
                [nodeId]: { ...node, parsedQuery },
              },
            };
          },
          undefined,
          'setParsedQuery',
        );
      },

      addResult: (nodeId, placeDcid, result) => {
        set(
          (state) => {
            const node = state.nodes[nodeId];
            if (!node) return state;
            return {
              nodes: {
                ...state.nodes,
                [nodeId]: {
                  ...node,
                  results: { ...node.results, [placeDcid]: result },
                },
              },
            };
          },
          undefined,
          'addResult',
        );
      },

      completeQuery: (nodeId, cardIds) => {
        set(
          (state) => {
            const node = state.nodes[nodeId];
            if (!node) return state;
            return {
              nodes: {
                ...state.nodes,
                [nodeId]: { ...node, status: 'complete', cardIds },
              },
              latestNodeId: nodeId,
            };
          },
          undefined,
          'completeQuery',
        );
      },

      failQuery: (nodeId) => {
        set(
          (state) => {
            const node = state.nodes[nodeId];
            if (!node) return state;
            return {
              nodes: {
                ...state.nodes,
                [nodeId]: { ...node, status: 'error' },
              },
            };
          },
          undefined,
          'failQuery',
        );
      },

      registerCard: (
        shapeId,
        historyNodeId,
        type,
        placeDcid,
        variableDcid?,
      ) => {
        set(
          (state) => ({
            cards: {
              ...state.cards,
              [shapeId]: {
                shapeId,
                historyNodeId,
                type,
                placeDcid,
                variableDcid,
              },
            },
          }),
          undefined,
          'registerCard',
        );
      },

      unregisterCard: (shapeId) => {
        set(
          (state) => {
            const { [shapeId]: _, ...rest } = state.cards;
            return { cards: rest };
          },
          undefined,
          'unregisterCard',
        );
      },

      cancelQuery: (nodeId) => {
        set(
          (state) => {
            const node = state.nodes[nodeId];
            if (!node) return state;

            const { [nodeId]: _, ...remainingNodes } = state.nodes;
            const remainingCards = Object.fromEntries(
              Object.entries(state.cards).filter(
                ([, card]) => card.historyNodeId !== nodeId,
              ),
            );

            return {
              nodes: remainingNodes,
              cards: remainingCards,
              latestNodeId:
                state.latestNodeId === nodeId
                  ? (node.parentId ?? null)
                  : state.latestNodeId,
              isProcessing: false,
              currentStatus: '',
            };
          },
          undefined,
          'cancelQuery',
        );
      },

      setIsProcessing: (val) =>
        set({ isProcessing: val }, undefined, 'setIsProcessing'),
      setCurrentStatus: (val) =>
        set({ currentStatus: val }, undefined, 'setCurrentStatus'),

      getAncestorChain: (nodeId) => {
        if (!nodeId) return [];
        const { nodes } = get();
        const chain: HistoryNode[] = [];
        let currentId: string | null = nodeId;

        while (currentId && chain.length < MAX_ANCESTOR_CHAIN) {
          const node: HistoryNode | undefined = nodes[currentId];
          if (!node) break;
          chain.unshift(node);
          currentId = node.parentId;
        }

        return chain;
      },

      getContextNodeId: (selectedShapeIds) => {
        const { cards, nodes, latestNodeId } = get();

        if (selectedShapeIds.length === 0) {
          return latestNodeId;
        }

        let bestNodeId: string | null = null;
        let bestTimestamp = 0;

        for (const shapeId of selectedShapeIds) {
          const card = cards[shapeId];
          if (!card) continue;
          const node = nodes[card.historyNodeId];
          if (!node) continue;
          if (node.timestamp > bestTimestamp) {
            bestTimestamp = node.timestamp;
            bestNodeId = node.id;
          }
        }

        return bestNodeId || latestNodeId;
      },

      getSelectedEntityDcids: (selectedShapeIds) => {
        const { cards, nodes } = get();
        const dcids: string[] = [];

        for (const shapeId of selectedShapeIds) {
          const card = cards[shapeId];
          if (!card) continue;
          const node = nodes[card.historyNodeId];
          if (!node) continue;
          const result = node.results[card.placeDcid];
          if (!result) continue;
          for (const entity of result.entities) {
            dcids.push(entity.dcid);
          }
        }

        return dcids;
      },
    }),
    { name: 'DataWeaverStore' },
  ),
);
