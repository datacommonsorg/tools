// --- Store types ---

export interface ParsedQuery {
  places: string[];
  topic: string;
  titles: Record<string, string>;
  dateRange?: { start?: string; end?: string };
  isFollowUp: boolean;
}

export interface HistoryNode {
  id: string;
  parentId: string | null;
  query: string;
  parsedQuery: ParsedQuery | null;
  cardIds: string[];
  timestamp: number;
  status: 'pending' | 'complete' | 'error';
}

type CardType =
  | 'loading'
  | 'html'
  | 'dataset'
  | 'comparison'
  | 'image'
  | 'query_result';

export interface CardEntry {
  shapeId: string;
  historyNodeId: string;
  type: CardType;
  variableDcids: string[];
  entityDcids: string[];
  title: string;
  variables?: ChartVariable[];
  metadata?: ChartMetadata[];
  summary?: string;
  insight?: string;
  followUps?: string[];
}

// --- Chart Specification types ---

export type ChartType = 'line_chart' | 'bar_chart' | 'comparison' | 'table';

export interface ChartVariable {
  dcid: string;
  name: string;
  rationale?: string;
}

interface ChartEntity {
  dcid: string;
  name: string;
}

export interface QueryResult {
  id: string;
  chartType: ChartType;
  title: string;
  variables: ChartVariable[];
  entities: ChartEntity[];
  metadata: ChartMetadata[];
  dateRange?: { start?: string; end?: string };
  summary?: string;
  insight?: string;
  followUps?: string[];
}

export interface FacetInfo {
  facetId: string;
  source: string;
  sourceUrl: string;
  unit: string;
  earliestDate: string;
  latestDate: string;
  observationCount: number;
  measurementMethod?: string;
  observations: Array<{ date: string; value: number }>;
}

export interface ChartMetadata {
  variableDcid: string;
  entityDcid: string;
  facets: FacetInfo[];
}

// --- MCP types ---

interface McpTool {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

export interface McpToolsListResult {
  tools: McpTool[];
}

export interface McpToolCallResult {
  content: Array<{ type: string; text?: string; [key: string]: unknown }>;
}

// --- API Request/Response types ---

/** Single request the frontend sends to /api/query — the backend handles everything. */
export interface QueryStreamRequest {
  query: string;
  atlasContext: string;
  ancestorChain: { query: string; topic: string; places: string[] }[];
  selectedEntityDcids: string[];
}

// --- SSE Stream event types ---

export const STREAM_EVENT = {
  status: 'status',
  parsedQuery: 'parsed_query',
  toolCall: 'tool_call',
  queryResult: 'query_result',
  complete: 'complete',
  error: 'error',
} as const;

export type StreamEvent =
  | { type: typeof STREAM_EVENT.status; message: string }
  | { type: typeof STREAM_EVENT.parsedQuery; data: ParsedQuery }
  | {
      type: typeof STREAM_EVENT.toolCall;
      tool: string;
      args: Record<string, unknown>;
    }
  | {
      type: typeof STREAM_EVENT.queryResult;
      result: QueryResult;
      place: string;
    }
  | { type: typeof STREAM_EVENT.complete; message: string }
  | { type: typeof STREAM_EVENT.error; message: string };
