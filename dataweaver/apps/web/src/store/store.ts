import { nanoid } from 'nanoid';
import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import { formatChartCardTitle } from '~/functions/format_card_title';
import { resolveResultForPlace } from '~/functions/scope_key';
import type {
  CardEntry,
  CardType,
  ChartStyle,
  ComparisonResult,
  FollowUp,
  FollowUpContext,
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
  focusTarget: { shapeId: string; sourceShapeId: string } | null;

  // --- Actions ---
  queryStart: (
    query: string,
    parsedQuery: ParsedQuery | null,
    parentNodeId: string | null,
    followUpContext?: FollowUpContext,
  ) => string;
  nodeSetParsedQuery: (nodeId: string, parsedQuery: ParsedQuery) => void;
  nodeAddResult: (
    nodeId: string,
    placeDcid: string,
    result: QueryResult,
  ) => void;
  nodeSetComparison: (nodeId: string, result: ComparisonResult) => void;
  nodeSetFollowUp: (nodeId: string, followUp: FollowUp) => void;
  queryComplete: (nodeId: string, cardIds: string[]) => void;
  queryFail: (nodeId: string) => void;
  cardRegister: (
    shapeId: string,
    historyNodeId: string,
    type: CardType,
    placeDcid: string,
    variableDcid?: string,
    parentPlaceDcid?: string,
  ) => void;
  cardRegisterBatch: (entries: CardEntry[]) => void;
  cardRegisterChart: (
    parentShapeId: string,
    placeDcid: string,
    variableDcid?: string,
  ) => void;
  cardUnregister: (shapeId: string) => void;
  cardClearFocusTarget: () => void;
  cardSetChartStyle: (shapeId: string, chartStyle: ChartStyle) => void;
  queryCancel: (nodeId: string) => void;
  nodeDismissFollowUp: (nodeId: string) => void;
  querySetProcessing: (val: boolean) => void;
  querySetStatus: (val: string) => void;

  // --- Selectors ---
  getAncestorChain: (nodeId: string | null) => HistoryNode[];
  getContextNodeId: (selectedShapeIds: string[]) => string | null;
  getSelectedEntityDcids: (selectedShapeIds: string[]) => string[];
  getResultsForSelectedCards: (selectedShapeIds: string[]) => QueryResult[];
}

/**
 * Remove a node and its associated cards from state. Returns the partial
 * state update, or `null` if the node doesn't exist.
 */
const removeNode = (
  state: AtlasStore,
  nodeId: string,
): Pick<AtlasStore, 'nodes' | 'cards' | 'latestNodeId'> | null => {
  const node = state.nodes[nodeId];
  if (!node) return null;

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
  };
};

export const useAtlasStore = create<AtlasStore>()(
  subscribeWithSelector(
    devtools(
      (set, get) => ({
        nodes: {},
        latestNodeId: null,
        cards: {},
        isProcessing: false,
        currentStatus: '',
        focusTarget: null,

        queryStart: (query, parsedQuery, parentNodeId, followUpContext) => {
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
            followUpContext,
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

        nodeSetComparison: (nodeId, comparison) => {
          set(
            (state) => {
              const node = state.nodes[nodeId];
              if (!node) return state;
              return {
                nodes: {
                  ...state.nodes,
                  [nodeId]: { ...node, comparison },
                },
              };
            },
            undefined,
            'nodeSetComparison',
          );
        },

        nodeSetFollowUp: (nodeId, followUp) => {
          set(
            (state) => {
              const node = state.nodes[nodeId];
              if (!node) return state;
              return {
                nodes: {
                  ...state.nodes,
                  [nodeId]: { ...node, followUp },
                },
              };
            },
            undefined,
            'nodeSetFollowUp',
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
          parentPlaceDcid?,
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
                  parentPlaceDcid,
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

        cardRegisterChart: (parentShapeId, placeDcid, variableDcid?) => {
          const { cards, nodes, cardRegister } = get();
          const parent = cards[parentShapeId];
          if (!parent) return;

          const node = nodes[parent.historyNodeId];

          // Determine effectiveParentPlaceDcid:
          // If the parent card belongs to or is an enclosing region, and the target
          // place is a child entity inside it, record that enclosing region as parentPlaceDcid.
          const parentDatasetKey = parent.parentPlaceDcid || parent.placeDcid;
          let effectiveParentPlaceDcid: string | undefined;

          if (parentDatasetKey && parent.placeDcid !== '__comparison') {
            if (parent.parentPlaceDcid && placeDcid === parent.placeDcid) {
              effectiveParentPlaceDcid = parent.parentPlaceDcid;
            } else if (parentDatasetKey !== placeDcid) {
              const parentResult = resolveResultForPlace(
                node?.results,
                parentDatasetKey,
              );
              if (
                parentResult?.placeDcid !== placeDcid &&
                parentResult?.entities?.some((e) => e.dcid === placeDcid)
              ) {
                effectiveParentPlaceDcid = parentDatasetKey;
              }
            }
          }

          const result = resolveResultForPlace(
            node?.results,
            effectiveParentPlaceDcid || placeDcid,
          );
          const plottableVar = result?.timeSeries.find(
            (ts) => (ts.facets[0]?.observations.length ?? 0) > 0,
          )?.variableDcid;
          const effectiveVar =
            variableDcid ||
            parent.variableDcid ||
            plottableVar ||
            result?.variables[0]?.dcid;

          const shapeId = `shape:${parent.historyNodeId}__${placeDcid}__chart${effectiveVar ? `__${effectiveVar}` : ''}`;
          if (cards[shapeId]) {
            set(
              { focusTarget: { shapeId, sourceShapeId: parent.shapeId } },
              undefined,
              'cardFocusTarget',
            );
            return;
          }

          cardRegister(
            shapeId,
            parent.historyNodeId,
            'chart',
            placeDcid,
            effectiveVar,
            effectiveParentPlaceDcid,
          );
          set(
            { focusTarget: { shapeId, sourceShapeId: parent.shapeId } },
            undefined,
            'cardFocusTarget',
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

        cardClearFocusTarget: () => {
          set({ focusTarget: null }, undefined, 'cardClearFocusTarget');
        },

        cardSetChartStyle: (shapeId, chartStyle) => {
          set(
            (state) => {
              const card = state.cards[shapeId];
              if (!card) return state;
              return {
                cards: {
                  ...state.cards,
                  [shapeId]: { ...card, chartStyle },
                },
              };
            },
            undefined,
            'cardSetChartStyle',
          );
        },

        queryCancel: (nodeId) => {
          set(
            (state) => {
              const base = removeNode(state, nodeId);
              if (!base) return state;
              return {
                ...base,
                isProcessing: false,
                currentStatus: '',
              };
            },
            undefined,
            'queryCancel',
          );
        },

        nodeDismissFollowUp: (nodeId) => {
          set(
            (state) => removeNode(state, nodeId) ?? state,
            undefined,
            'nodeDismissFollowUp',
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
            if (card.parentPlaceDcid) {
              dcids.add(card.placeDcid);
              continue;
            }
            const node = nodes[card.historyNodeId];
            if (!node) continue;
            const result = resolveResultForPlace(node.results, card.placeDcid);
            if (!result) continue;
            for (const entity of result.entities) {
              dcids.add(entity.dcid);
            }
          }
          return Array.from(dcids);
        },

        getResultsForSelectedCards: (selectedShapeIds) => {
          const { cards, nodes } = get();
          const seen = new Set<string>();
          const results: QueryResult[] = [];

          for (const shapeId of selectedShapeIds) {
            const card = cards[shapeId];
            if (!card || card.type !== 'chart') continue;

            const node = nodes[card.historyNodeId];
            if (!node) continue;

            if (card.placeDcid === '__comparison') {
              // Comparison chart — extract all per-place results from the node.
              for (const [key, result] of Object.entries(node.results)) {
                const placeKey =
                  result.placeDcid ||
                  (key.includes(':') ? key.split(':')[0] : key) ||
                  result.entities[0]?.dcid;
                if (!placeKey || seen.has(placeKey)) continue;
                seen.add(placeKey);
                results.push(result);
              }
            } else {
              // Regular chart — extract the single place result.
              const resultKey = card.parentPlaceDcid || card.placeDcid;
              const result = resolveResultForPlace(node.results, resultKey);
              if (!result) continue;

              // If the card is scoped to a specific child place (e.g. South Africa from an Africa map)
              if (card.parentPlaceDcid) {
                const dedupeKey = card.variableDcid
                  ? `${card.placeDcid}::${card.variableDcid}`
                  : card.placeDcid;
                if (seen.has(dedupeKey)) continue;
                seen.add(dedupeKey);

                const entity = result.entities.find(
                  (e) => e.dcid === card.placeDcid,
                );
                const placeName = entity?.name || card.placeDcid;
                const filteredTimeSeries = result.timeSeries.filter(
                  (entry) =>
                    entry.entityDcid === card.placeDcid &&
                    (!card.variableDcid ||
                      entry.variableDcid === card.variableDcid),
                );
                const filteredVariables = card.variableDcid
                  ? result.variables.filter(
                      (entry) => entry.dcid === card.variableDcid,
                    )
                  : result.variables;

                const cleanedVariables = filteredVariables.map((v) => ({
                  ...v,
                  isChildQuery: false,
                  parentPlaceDcid: undefined,
                  childPlaceType: undefined,
                  placeDcid: card.placeDcid,
                  placeName,
                }));

                results.push({
                  ...result,
                  id: `${result.id}__${card.placeDcid}`,
                  title: formatChartCardTitle(
                    cleanedVariables[0]?.name,
                    placeName,
                    false,
                  ),
                  placeDcid: card.placeDcid,
                  placeName,
                  isChildQuery: false,
                  parentPlaceDcid: undefined,
                  childPlaceType: undefined,
                  entities: entity
                    ? [entity]
                    : [{ dcid: card.placeDcid, name: placeName }],
                  variables: cleanedVariables,
                  timeSeries: filteredTimeSeries,
                });
                continue;
              }

              // Use a composite key based on card/result place scope and variable so that
              // different variables for the same place/region are treated as distinct results.
              const placeKey =
                card.placeDcid ||
                result.placeDcid ||
                result.parentPlaceDcid ||
                result.entities[0]?.dcid;
              if (!placeKey) continue;
              const dedupeKey = card.variableDcid
                ? `${placeKey}::${card.variableDcid}`
                : placeKey;
              if (seen.has(dedupeKey)) continue;
              seen.add(dedupeKey);

              // When the card targets a specific variable, return a narrowed
              // result containing only that variable's time series so the
              // combine API receives per-variable data.
              if (card.variableDcid) {
                const variable = result.variables.find(
                  (entry) => entry.dcid === card.variableDcid,
                );
                const timeSeries = result.timeSeries.filter(
                  (entry) => entry.variableDcid === card.variableDcid,
                );
                results.push({
                  ...result,
                  variables: variable ? [variable] : result.variables,
                  timeSeries,
                });
              } else {
                results.push(result);
              }
            }
          }

          return results;
        },
      }),
      { name: 'AtlasStore' },
    ),
  ),
);
