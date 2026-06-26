/**
 * @fileoverview Controlled React hook that streams an agent chat turn over
 * Server-Sent Events from the agent sidecar's `/agent/chat/stream` endpoint,
 * parses each event, and folds it into the turn state. Also defines the
 * domain types (turns, tool calls, thoughts, charts, provenance) shared
 * across the chat UI, plus the translation layer from the raw upstream VM
 * payload (snake_case) to the camelCase types used by components.
 */

import { useCallback, useState } from "react";

/** A single MCP tool invocation surfaced in the reasoning trail. */
export interface ToolCallEvent {
  name: string;
  arguments: Record<string, unknown>;
  status?: "success" | "error";
}

/** A streamed "thinking" fragment, tagged with the phase that produced it. */
export interface ThoughtEvent {
  text: string;
  phase: "mcp" | "kb" | "synthesis";
}

/**
 * A single chart to render. Mirrors the upstream VM payload
 * (mcp_proxy_only.py CHART_CONFIG_SCHEMA + homepage.html renderDCComponent),
 * translated to camelCase via {@link mapRawChartItem}.
 */
export interface ChartItem {
  vizType:
    | "line"
    | "bar"
    | "map"
    | "ranking"
    | "pie"
    | "highlight"
    | "gauge"
    | "scatter"
    | "slider";
  title?: string;
  variableDcids: string[];
  placeDcids?: string[];
  parentPlace?: string;
  childPlaceType?: string;
  date?: string;
  unit?: string;
}

/**
 * Chart configuration emitted by the agent for a turn. Supports the modern
 * multi-chart format (`charts: [...]`) and the legacy single-chart fallback
 * (chart fields at the top level). Translated from the raw payload via
 * {@link mapRawChartConfig}.
 */
export interface ChartConfig {
  shouldRender: boolean;
  hideCharts?: boolean;
  charts?: ChartItem[];
  // Legacy single-chart fallback fields (older agent versions emit these
  // alongside `shouldRender` instead of inside a `charts` array).
  vizType?: ChartItem["vizType"];
  title?: string;
  variableDcids?: string[];
  placeDcids?: string[];
  parentPlace?: string;
  childPlaceType?: string;
  date?: string;
}

/** A named data source (provenance) with a link back to the origin dataset. */
export interface ProvenanceItem {
  name: string;
  url: string;
}

/**
 * Lifecycle status of a chat turn. Union of literals (not an interface) so
 * it can be used both as a discriminator and a UI label key.
 */
export type TurnStatus =
  | "idle"
  | "mcp"
  | "kb"
  | "synthesis"
  | "done"
  | "error";

/** Accumulated state for a single user/agent exchange in the chat thread. */
export interface ChatTurn {
  userMessage: string;
  sessionId?: string;
  status: TurnStatus;
  toolCalls: ToolCallEvent[];
  thoughts: ThoughtEvent[];
  text: string;
  chartConfig?: ChartConfig;
  provenance: ProvenanceItem[];
  error?: string;
}

// ---------------------------------------------------------------------------
// Raw upstream payload shapes + translation layer
//
// The agent sidecar emits snake_case JSON. We keep `Raw*` interfaces that
// mirror that wire format exactly and translate to the camelCase domain
// types above at the boundary. This isolates UI components from upstream
// schema renames: a backend rename of `variable_dcids` → `variables` only
// touches the mappers here, not every component that reads the property.
// ---------------------------------------------------------------------------

/** Raw single-chart shape as received from the agent stream. */
interface RawChartItem {
  viz_type: ChartItem["vizType"];
  title?: string;
  variable_dcids?: string[];
  place_dcids?: string[];
  parent_place?: string;
  child_place_type?: string;
  date?: string;
  unit?: string;
}

/** Raw chart-config shape as received from the agent stream. */
interface RawChartConfig {
  should_render: boolean;
  hide_charts?: boolean;
  charts?: RawChartItem[];
  viz_type?: RawChartItem["viz_type"];
  title?: string;
  variable_dcids?: string[];
  place_dcids?: string[];
  parent_place?: string;
  child_place_type?: string;
  date?: string;
}

/** A single SSE event payload. Optional fields; an event may carry several. */
interface SseEvent {
  session_id?: string;
  status?: "mcp_start" | "kb_start" | "synthesis_start" | "success" | "error" | string;
  tool_call?: ToolCallEvent;
  name?: string;
  type?: string;
  arguments?: Record<string, unknown>;
  thought?: string;
  phase?: ThoughtEvent["phase"];
  text?: string;
  chart_config?: RawChartConfig; // Raw config received from stream
  mcp_sources?: ProvenanceItem[];
  kb_sources?: ProvenanceItem[];
  provenance?: ProvenanceItem[];
  done?: boolean;
  error?: string;
}

/** Translates a raw stream chart item into the camelCase {@link ChartItem}. */
function mapRawChartItem(raw: RawChartItem): ChartItem {
  return {
    vizType: raw.viz_type,
    title: raw.title,
    variableDcids: raw.variable_dcids ?? [],
    placeDcids: raw.place_dcids,
    parentPlace: raw.parent_place,
    childPlaceType: raw.child_place_type,
    date: raw.date,
    unit: raw.unit,
  };
}

/** Translates a raw stream chart config into the camelCase {@link ChartConfig}. */
function mapRawChartConfig(raw: RawChartConfig): ChartConfig {
  return {
    shouldRender: raw.should_render,
    hideCharts: raw.hide_charts,
    charts: raw.charts?.map(mapRawChartItem),
    vizType: raw.viz_type,
    title: raw.title,
    variableDcids: raw.variable_dcids,
    placeDcids: raw.place_dcids,
    parentPlace: raw.parent_place,
    childPlaceType: raw.child_place_type,
    date: raw.date,
  };
}

const newTurn = (userMessage: string): ChatTurn => ({
  userMessage,
  status: "idle",
  toolCalls: [],
  thoughts: [],
  text: "",
  provenance: [],
});

// SSE framing constants. The Python proxy emits a single `data: {json}\n\n`
// per event, so events are separated by a blank line and each data line is
// prefixed with `data:`.
const SSE_EVENT_SEPARATOR = "\n\n";
const SSE_EVENT_DATA_PREFIX = "data:";

/**
 * Stream parser: splits the SSE chunks on the blank-line boundary, then on
 * each event extracts the `data:` payload as JSON. The Python proxy always
 * emits a single `data: {json}\n\n` per event, so we don't worry about
 * multi-line data payloads.
 */
async function* parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<SseEvent, void, unknown> {
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf(SSE_EVENT_SEPARATOR)) >= 0) {
      const rawEvent = buffer.slice(0, idx);
      buffer = buffer.slice(idx + SSE_EVENT_SEPARATOR.length);
      for (const line of rawEvent.split("\n")) {
        if (!line.startsWith(SSE_EVENT_DATA_PREFIX)) {
          continue;
        }
        const payload = line.slice(SSE_EVENT_DATA_PREFIX.length).trim();
        if (!payload) {
          continue;
        }
        try {
          yield JSON.parse(payload) as SseEvent;
        } catch (err) {
          // Malformed JSON — skip rather than break the stream, but warn so
          // a broken SSE payload is debuggable instead of silently dropped.
          console.warn("[use_sse_chat] skipping malformed SSE payload:", payload, err);
        }
      }
    }
  }
}

/** Return value of {@link useSseChat}. */
export interface UseSseChatResult {
  isStreaming: boolean;
  error: string | null;
  send: (message: string) => Promise<void>;
}

/**
 * Props for {@link useSseChat}.
 *
 * Controlled hook — turns and sessionId live in the parent
 * (ChatSessionProvider) so multiple chat threads can share one streaming
 * machine. Switching the current session is a parent-level decision; this
 * hook just reads/writes whichever turns array it's been pointed at.
 */
export interface UseSseChatProps {
  endpoint?: string;
  turns: ChatTurn[];
  setTurns: (updater: (prev: ChatTurn[]) => ChatTurn[]) => void;
  sessionId: string | undefined;
  setSessionId: (id: string | undefined) => void;
}

/**
 * Builds the Gemini-format chat history (role + parts.text) sent to the
 * agent. Excludes the in-flight turn, which the caller appends separately.
 */
function buildHistory(turns: ChatTurn[]) {
  return turns.flatMap((turn) => {
    const items: Array<{ role: string; parts: Array<{ text: string }> }> = [
      { role: "user", parts: [{ text: turn.userMessage }] },
    ];
    if (turn.text) {
      items.push({ role: "model", parts: [{ text: turn.text }] });
    }
    return items;
  });
}

/**
 * React hook that POSTs a message to the agent stream endpoint and folds the
 * resulting SSE events into the current chat turn.
 *
 * @param props Controlled turn/session state plus the optional endpoint.
 * @returns Streaming flag, last error, and a `send(message)` action.
 */
export function useSseChat(props: UseSseChatProps): UseSseChatResult {
  const {
    endpoint = "/agent/chat/stream",
    turns,
    setTurns,
    sessionId,
    setSessionId,
  } = props;
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(
    async (message: string) => {
      if (!message.trim()) {
        return;
      }
      const baseTurn = newTurn(message);
      let turnIndex = -1;
      setTurns((prev) => {
        turnIndex = prev.length;
        return [...prev, baseTurn];
      });
      setIsStreaming(true);
      setError(null);

      // History sent to the agent excludes the current turn.
      const history = buildHistory(turns);

      // `patch` applies an immutable update to just the in-flight turn,
      // leaving the rest of the turns array untouched. Bounds-checked so a
      // session switch mid-stream can't corrupt another thread's turns.
      const patch = (mutate: (turn: ChatTurn) => ChatTurn) =>
        setTurns((prev) => {
          if (turnIndex < 0 || turnIndex >= prev.length) {
            return prev;
          }
          const next = prev.slice();
          next[turnIndex] = mutate(next[turnIndex]);
          return next;
        });

      try {
        const resp = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            history,
            session_id: sessionId,
          }),
        });
        if (!resp.ok || !resp.body) {
          const errText = `HTTP ${resp.status} ${resp.statusText}`;
          patch((turn) => ({ ...turn, status: "error", error: errText }));
          setError(errText);
          return;
        }

        const reader = resp.body.getReader();
        for await (const evt of parseSseStream(reader)) {
          // The agent sometimes packs MULTIPLE fields into one event
          // (e.g. the final event has BOTH `chart_config` and `done`).
          // We apply each recognised field independently in one patch,
          // rather than using `if … continue` which would drop later
          // fields after the first match.
          patch((turn) => applyEvent(turn, evt));
          if (typeof evt.error === "string") {
            setError(evt.error);
          }
          if (typeof evt.session_id === "string") {
            setSessionId(evt.session_id);
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        patch((turn) => ({ ...turn, status: "error", error: msg }));
        setError(msg);
      } finally {
        setIsStreaming(false);
      }
    },
    [endpoint, turns, setTurns, sessionId, setSessionId],
  );

  return { isStreaming, error, send };
}

/**
 * Merges newly-received provenance items into the existing list, de-duping
 * by URL so the same source isn't listed twice across events.
 */
function mergeProvenance(
  existing: ProvenanceItem[],
  incoming: ProvenanceItem[],
): ProvenanceItem[] {
  const seen = new Set(existing.map((item) => item.url));
  const merged = [...existing];
  for (const source of incoming) {
    if (source && source.url && !seen.has(source.url)) {
      merged.push(source);
      seen.add(source.url);
    }
  }
  return merged;
}

/**
 * Pure reducer: applies every recognised field of an SSE event to the turn
 * state. The agent sometimes packs multiple fields into one event (e.g. the
 * closing event has both `chart_config` AND `done` — an `if … continue`
 * style would silently drop the second field). Every field is independent
 * and additive.
 */
function applyEvent(turn: ChatTurn, evt: SseEvent): ChatTurn {
  let next = turn;

  if (typeof evt.session_id === "string") {
    next = { ...next, sessionId: evt.session_id };
  }

  if (evt.status === "mcp_start") {
    next = { ...next, status: "mcp" };
  } else if (evt.status === "kb_start") {
    next = { ...next, status: "kb" };
  } else if (evt.status === "synthesis_start") {
    next = { ...next, status: "synthesis" };
  }

  if (evt.tool_call) {
    next = {
      ...next,
      toolCalls: [...next.toolCalls, evt.tool_call],
    };
  }
  // Some agent versions also emit the tool result inline as its own field.
  if (evt.name && evt.type === "tool_call") {
    const tc: ToolCallEvent = {
      name: evt.name,
      arguments: evt.arguments ?? {},
      status: evt.status === "success" || evt.status === "error" ? evt.status : undefined,
    };
    next = { ...next, toolCalls: [...next.toolCalls, tc] };
  }

  if (typeof evt.thought === "string") {
    const phase = evt.phase ?? "synthesis";
    next = {
      ...next,
      thoughts: [...next.thoughts, { text: evt.thought, phase }],
    };
  }

  if (typeof evt.text === "string") {
    next = { ...next, text: next.text + evt.text };
  }

  if (evt.chart_config) {
    next = { ...next, chartConfig: mapRawChartConfig(evt.chart_config) };
  }

  const sourceList =
    (Array.isArray(evt.mcp_sources) ? evt.mcp_sources : null) ??
    (Array.isArray(evt.kb_sources) ? evt.kb_sources : null) ??
    (Array.isArray(evt.provenance) ? evt.provenance : null);
  if (sourceList) {
    next = { ...next, provenance: mergeProvenance(next.provenance, sourceList) };
  }

  if (evt.done) {
    next = { ...next, status: "done" };
  }

  if (typeof evt.error === "string") {
    next = { ...next, status: "error", error: evt.error };
  }

  return next;
}
