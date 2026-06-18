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
  /** Query results keyed by entity (place) DCID. */
  results: Record<string, QueryResult>;
  cardIds: string[];
  timestamp: number;
  status: 'pending' | 'complete' | 'error';
}

export type CardType = 'loading' | 'table' | 'notes' | 'chart';

export interface Insight {
  title: string;
  text: string;
}

export interface CardEntry {
  shapeId: string;
  historyNodeId: string;
  type: CardType;
  /** Key into the parent HistoryNode's `results` record. */
  placeDcid: string;
}

// --- Chart Specification types ---

export interface ChartVariable {
  dcid: string;
  name: string;
  rationale?: string;
}

export interface ChartEntity {
  dcid: string;
  name: string;
}

export interface QueryResult {
  id: string;
  title: string;
  variables: ChartVariable[];
  entities: ChartEntity[];
  metadata: ChartMetadata[];
  dateRange?: { start?: string; end?: string };
  introduction?: string;
  coverage?: string;
  insights?: Insight[];
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

// --- Status messages ---

export const STATUS = {
  // Terminal states (for programmatic checks)
  idle: '',
  complete: 'Complete.',
  stopped: 'Stopped',

  // Static messages
  starting: 'Starting query...',
  connecting: 'Connecting...',
  checkingSafety: 'Checking query safety...',
  parsingQuery: 'Parsing query...',
  fetchingTools: 'Fetching available tools...',
  noResponseBody: 'No response body',

  // Dynamic messages
  discoveringMetrics: (place: string, current: number, total: number) =>
    `Discovering metrics for ${place} (${current}/${total})...`,
  usingTool: (tool: string, count: number, max: number) =>
    `Using tool: ${tool} (${count}/${max})...`,
  noResponse: (place: string) => `No response for ${place}, skipping...`,
  buildingResults: (place: string) => `Building results for ${place}...`,
  invalidResponse: (place: string) =>
    `Invalid model response for ${place}, skipping...`,
  noVariables: (place: string) => `No variables found for ${place}.`,
  invalidDcid: (place: string) =>
    `Could not resolve a valid DCID for ${place}, skipping...`,
  loadingMetadata: (place: string, varCount: number) =>
    `Loading metadata for ${place} (${varCount} variables)...`,
  apiError: (status: number, body: string) => `API error: ${status} ${body}`,
} as const;

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
