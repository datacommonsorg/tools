import { nanoid } from 'nanoid';
import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import type {
  CardEntry,
  CardType,
  HistoryNode,
  ParsedQuery,
  QueryResult,
} from '~/server/types';

const MAX_ANCESTOR_CHAIN = 10;

export interface AtlasStore {
  // --- History ---
  nodes: Record<string, HistoryNode>;
  latestNodeId: string | null;

  // --- Card registry ---
  cards: Record<string, CardEntry>;

  // --- UI state ---
  isProcessing: boolean;
  currentStatus: string;

  // --- Actions ---
  queryStart: (
    query: string,
    parsedQuery: ParsedQuery | null,
    parentNodeId: string | null,
  ) => string;
  nodeSetParsedQuery: (nodeId: string, parsedQuery: ParsedQuery) => void;
  nodeAddResult: (
    nodeId: string,
    placeDcid: string,
    result: QueryResult,
  ) => void;
  queryComplete: (nodeId: string, cardIds: string[]) => void;
  queryFail: (nodeId: string) => void;
  cardRegister: (
    shapeId: string,
    historyNodeId: string,
    type: CardType,
    placeDcid: string,
    variableDcid?: string,
  ) => void;
  cardRegisterBatch: (entries: CardEntry[]) => void;
  cardRegisterChart: (
    parentShapeId: string,
    placeDcid: string,
    variableDcid: string,
  ) => void;
  cardUnregister: (shapeId: string) => void;
  queryCancel: (nodeId: string) => void;
  querySetProcessing: (val: boolean) => void;
  querySetStatus: (val: string) => void;

  // --- Selectors ---
  getAncestorChain: (nodeId: string | null) => HistoryNode[];
  getContextNodeId: (selectedShapeIds: string[]) => string | null;
  getSelectedEntityDcids: (selectedShapeIds: string[]) => string[];
}

export const useAtlasStore = create<AtlasStore>()(
  subscribeWithSelector(
    devtools(
      (set, get) => ({
        nodes: {},
        latestNodeId: null,
        cards: {},
        isProcessing: false,
        currentStatus: '',

        queryStart: (query, parsedQuery, parentNodeId) => {
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
            'queryStart',
          );
          return id;
        },

        nodeSetParsedQuery: (nodeId, parsedQuery) => {
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
            'nodeSetParsedQuery',
          );
        },

        nodeAddResult: (nodeId, placeDcid, result) => {
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
            'nodeAddResult',
          );
        },

        queryComplete: (nodeId, cardIds) => {
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
            'queryComplete',
          );
        },

        queryFail: (nodeId) => {
          set(
            (state) => {
              const node = state.nodes[nodeId];
              if (!node) return state;

              const remainingCards = Object.fromEntries(
                Object.entries(state.cards).filter(
                  ([, card]) => card.historyNodeId !== nodeId,
                ),
              );

              return {
                nodes: {
                  ...state.nodes,
                  [nodeId]: { ...node, status: 'error' },
                },
                cards: remainingCards,
              };
            },
            undefined,
            'queryFail',
          );
        },

        cardRegister: (
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
            'cardRegister',
          );
        },

        cardRegisterBatch: (entries) => {
          set(
            (state) => ({
              cards: {
                ...state.cards,
                ...Object.fromEntries(
                  entries.map((entry) => [entry.shapeId, entry]),
                ),
              },
            }),
            undefined,
            'cardRegisterBatch',
          );
        },

        cardRegisterChart: (parentShapeId, placeDcid, variableDcid) => {
          const { cards, cardRegister } = get();
          const parent = cards[parentShapeId];
          if (!parent) return;

          const shapeId = `shape:${parent.historyNodeId}__${placeDcid}__chart__${variableDcid}`;
          if (cards[shapeId]) return;

          cardRegister(
            shapeId,
            parent.historyNodeId,
            'chart',
            placeDcid,
            variableDcid,
          );
        },

        cardUnregister: (shapeId) => {
          set(
            (state) => {
              const { [shapeId]: _, ...rest } = state.cards;
              return { cards: rest };
            },
            undefined,
            'cardUnregister',
          );
        },

        queryCancel: (nodeId) => {
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
            'queryCancel',
          );
        },

        querySetProcessing: (val) =>
          set({ isProcessing: val }, undefined, 'querySetProcessing'),
        querySetStatus: (val) =>
          set({ currentStatus: val }, undefined, 'querySetStatus'),

        getAncestorChain: (nodeId) => {
          if (!nodeId) return [];
          const { nodes } = get();
          const chain: HistoryNode[] = [];
          let currentId: string | null = nodeId;

          const visited = new Set<string>();
          while (currentId && chain.length < MAX_ANCESTOR_CHAIN) {
            if (visited.has(currentId)) break;
            visited.add(currentId);
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
          const dcids = new Set<string>();
          for (const shapeId of selectedShapeIds) {
            const card = cards[shapeId];
            if (!card) continue;
            const node = nodes[card.historyNodeId];
            if (!node) continue;
            const result = node.results[card.placeDcid];
            if (!result) continue;
            for (const entity of result.entities) {
              dcids.add(entity.dcid);
            }
          }
          return Array.from(dcids);
        },
      }),
      { name: 'AtlasStore' },
    ),
  ),
);
