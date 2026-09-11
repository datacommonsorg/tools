import { nanoid } from 'nanoid';
import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';
import {
  buildCardShapeId,
  COMPARISON_PLACE_KEY,
} from '~/functions/card_shape_id';
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
    resultPlaceDcid?: string,
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
          resultPlaceDcid?,
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
                  resultPlaceDcid,
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

          // Determine effectiveResultPlaceDcid:
          // If the parent card belongs to or is an enclosing region, and the target
          // place is a child entity inside it, record that enclosing region as the
          // key its observations must be read from.
          const parentDatasetKey = parent.resultPlaceDcid || parent.placeDcid;
          let effectiveResultPlaceDcid: string | undefined;

          if (parentDatasetKey && parent.placeDcid !== COMPARISON_PLACE_KEY) {
            if (parent.resultPlaceDcid && placeDcid === parent.placeDcid) {
              effectiveResultPlaceDcid = parent.resultPlaceDcid;
            } else if (parentDatasetKey !== placeDcid) {
              const parentResult = resolveResultForPlace(
                node?.results,
                parentDatasetKey,
              );
              if (
                parentResult?.placeDcid !== placeDcid &&
                parentResult?.entities?.some((e) => e.dcid === placeDcid)
              ) {
                effectiveResultPlaceDcid = parentDatasetKey;
              }
            }
          }

          const result = resolveResultForPlace(
            node?.results,
            effectiveResultPlaceDcid || placeDcid,
          );

          // A card is only renderable when some facet of the target variable
          // carries observations for the target place. Child cards read a
          // single entity out of the enclosing region's result, so they must
          // match on entity too.
          const isPlottable = (candidate: string | undefined): boolean =>
            candidate !== undefined &&
            (result?.timeSeries.some(
              (ts) =>
                ts.variableDcid === candidate &&
                (!effectiveResultPlaceDcid || ts.entityDcid === placeDcid) &&
                ts.facets.some((f) => f.observations.length > 0),
            ) ??
              false);

          const plottableVar = result?.timeSeries.find(
            (ts) =>
              (!effectiveResultPlaceDcid || ts.entityDcid === placeDcid) &&
              ts.facets.some((f) => f.observations.length > 0),
          )?.variableDcid;

          // Inherit the parent card's variable so a drill-down keeps the metric
          // the user was looking at — but only when that metric has data for
          // the target place, otherwise fall back to the first one that does.
          const effectiveVar =
            variableDcid ||
            (isPlottable(parent.variableDcid)
              ? parent.variableDcid
              : undefined) ||
            plottableVar;

          const shapeId = buildCardShapeId({
            historyNodeId: parent.historyNodeId,
            placeDcid,
            type: 'chart',
            variableDcid: effectiveVar,
          });
          if (cards[shapeId]) {
            set(
              { focusTarget: { shapeId, sourceShapeId: parent.shapeId } },
              undefined,
              'cardFocusTarget',
            );
            return;
          }

          // Nothing to draw: the shape sync would skip this card, leaving a
          // registry entry with no shape on the canvas — and the duplicate
          // check above would then swallow every retry. Bail out instead.
          if (!isPlottable(effectiveVar)) return;

          cardRegister(
            shapeId,
            parent.historyNodeId,
            'chart',
            placeDcid,
            effectiveVar,
            effectiveResultPlaceDcid,
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
            if (card.resultPlaceDcid) {
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

            if (card.placeDcid === COMPARISON_PLACE_KEY) {
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
              const resultKey = card.resultPlaceDcid || card.placeDcid;
              const result = resolveResultForPlace(node.results, resultKey);
              if (!result) continue;

              // If the card is scoped to a specific child place (e.g. South Africa from an Africa map)
              if (card.resultPlaceDcid) {
                // Deliberately the same `place::variable` namespace as the
                // regular branch below: a child card and a same-place regular
                // card describe the same place/variable pair, so the combine
                // API should only receive it once.
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
                  id: `${result.id}__${card.placeDcid}${card.variableDcid ? `__${card.variableDcid}` : ''}`,
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
                  id: `${result.id}__${card.variableDcid}`,
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
