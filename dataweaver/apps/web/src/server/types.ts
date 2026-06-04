// --- Store types ---

export interface ParsedQuery {
  places: string[];
  topic: string;
  titles: Record<string, string>;
  dateRange?: { start?: string; end?: string };
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
  type: CardType;
  variableDcids: string[];
  entityDcids: string[];
  title: string;
}

// --- Chart Specification types ---

export type ChartType = 'line_chart' | 'bar_chart' | 'comparison' | 'table';

interface ChartVariable {
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

interface ChartMetadata {
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
  selectedEntityDcids: string[];
}

// --- SSE Stream event types ---

export type StreamEvent =
  | { type: 'status'; message: string }
  | { type: 'parsed_query'; data: ParsedQuery }
  | { type: 'tool_call'; tool: string; args: Record<string, unknown> }
  | { type: 'query_result'; result: QueryResult; place: string }
  | { type: 'metadata'; data: ChartMetadata }
  | { type: 'complete' }
  | { type: 'error'; message: string };
