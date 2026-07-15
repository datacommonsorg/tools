/**
 * @fileoverview Provides the SSE chat hook: streams agent responses and reduces events into chat turns.
 */

import { useCallback, useRef, useState } from "react";

/** SSE framing: events are separated by a blank line. */
const SSE_EVENT_SEPARATOR = "\n\n";
/** SSE framing: payload lines are prefixed with `data:`. */
const SSE_EVENT_DATA_PREFIX = "data:";

/**
 * A tool invocation emitted by the agent sidecar's /agent/chat/stream
 * endpoint. Mirrors what mcp_proxy_only.py's chat_stream() generator produces.
 */
export interface ToolCallEvent {
  name: string;
  arguments: Record<string, unknown>;
  status?: "success" | "error";
}

/** A reasoning snippet emitted while the agent works, tagged by pipeline phase. */
export interface ThoughtEvent {
  text: string;
  phase: "mcp" | "kb" | "synthesis";
}

/**
 * One chart the agent asks the UI to render, in the UI's camelCase domain
 * shape. Produced by {@link mapRawChartItem} from the snake_case
 * {@link RawChartItem} wire format.
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
 * The agent's chart-rendering directive for a turn, in camelCase domain shape.
 * Produced by {@link mapRawChartConfig} from the snake_case
 * {@link RawChartConfig} wire format. Supports the modern multi-chart format
 * (`charts: [...]`); legacy single-chart fallback fields are folded into
 * `charts` during mapping.
 */
export interface ChartConfig {
  shouldRender: boolean;
  hideCharts?: boolean;
  charts?: ChartItem[];
}

/**
 * Wire format of one chart item as emitted by the agent
 * (mcp_proxy_only.py CHART_CONFIG_SCHEMA + homepage.html renderDCComponent).
 * snake_case matches the SSE payload; {@link mapRawChartItem} converts to the
 * camelCase {@link ChartItem} the UI consumes, so an upstream schema rename
 * only requires updating the mapper.
 */
interface RawChartItem {
  viz_type: ChartItem["vizType"];
  title?: string;
  variable_dcids: string[];
  place_dcids?: string[];
  parent_place?: string;
  child_place_type?: string;
  date?: string;
  unit?: string;
}

/**
 * Wire format of the chart_config SSE field. Older agent versions emit the
 * legacy single-chart fields (`viz_type`, `variable_dcids`, …) at the top
 * level instead of inside a `charts` array; {@link mapRawChartConfig}
 * normalises both shapes.
 */
interface RawChartConfig {
  should_render: boolean;
  hide_charts?: boolean;
  charts?: RawChartItem[];
  viz_type?: ChartItem["vizType"];
  title?: string;
  variable_dcids?: string[];
  place_dcids?: string[];
  parent_place?: string;
  child_place_type?: string;
  date?: string;
}

/** Converts one raw snake_case chart item into the camelCase domain shape. */
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

/**
 * Converts the raw chart_config payload into the camelCase domain shape,
 * folding the legacy top-level single-chart fields into a one-element
 * `charts` array when no modern `charts` list is present.
 */
function mapRawChartConfig(raw: RawChartConfig): ChartConfig {
  let charts = raw.charts?.map(mapRawChartItem);
  if ((!charts || charts.length === 0) && raw.variable_dcids?.length) {
    charts = [
      mapRawChartItem({
        viz_type: raw.viz_type ?? "line",
        title: raw.title,
        variable_dcids: raw.variable_dcids,
        place_dcids: raw.place_dcids,
        parent_place: raw.parent_place,
        child_place_type: raw.child_place_type,
        date: raw.date,
      }),
    ];
  }
  return {
    shouldRender: raw.should_render,
    hideCharts: raw.hide_charts,
    charts,
  };
}

/** A source attribution (display name + link) surfaced with an answer. */
export interface ProvenanceItem { name: string; url: string }

/** Lifecycle of one chat turn, driven by the agent's status events. */
export type TurnStatus =
  | "idle"
  | "mcp"
  | "kb"
  | "synthesis"
  | "done"
  | "error";

/** Accumulated UI state for one user message and its streamed response. */
export interface ChatTurn {
  userMessage: string;
  sessionId?: string;
  status: TurnStatus;
  toolCalls: ToolCallEvent[];
  thoughts: ThoughtEvent[];
  text: string;
  chartConfig?: ChartConfig;
  provenance: ProvenanceItem[];
  /** Self-contained follow-up questions emitted by the agent after `done`. */
  followUps?: string[];
  error?: string;
}

/**
 * One decoded SSE event from /agent/chat/stream. The agent packs a varying
 * subset of these fields into each event (the closing event, for example,
 * carries both `chart_config` and `done`), so every field is optional.
 */
interface SseEvent {
  session_id?: string;
  status?: "mcp_start" | "kb_start" | "synthesis_start" | "success" | "error" | string;
  tool_call?: ToolCallEvent;
  /** Inline tool-call fields (some agent versions emit these instead of `tool_call`). */
  name?: string;
  type?: string;
  arguments?: Record<string, unknown>;
  thought?: string;
  phase?: ThoughtEvent["phase"];
  text?: string;
  chart_config?: RawChartConfig;
  follow_up_questions?: string[];
  mcp_sources?: ProvenanceItem[];
  kb_sources?: ProvenanceItem[];
  provenance?: ProvenanceItem[];
  done?: boolean;
  error?: string;
}

const newTurn = (userMessage: string): ChatTurn => ({
  userMessage,
  status: "idle",
  toolCalls: [],
  thoughts: [],
  text: "",
  provenance: [],
});

/**
 * Parses the SSE byte stream into decoded events.
 *
 * Splits chunks on the blank-line event boundary, then extracts each `data:`
 * payload as JSON. The Python proxy always emits a single `data: {json}\n\n`
 * per event, so multi-line data payloads are not a concern.
 */
async function* parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<SseEvent, void, unknown> {
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf(SSE_EVENT_SEPARATOR)) >= 0) {
      const rawEvent = buffer.slice(0, idx);
      buffer = buffer.slice(idx + SSE_EVENT_SEPARATOR.length);
      for (const line of rawEvent.split("\n")) {
        if (!line.startsWith(SSE_EVENT_DATA_PREFIX)) continue;
        const payload = line.slice(SSE_EVENT_DATA_PREFIX.length).trim();
        if (!payload) continue;
        try {
          yield JSON.parse(payload) as SseEvent;
        } catch {
          // Malformed JSON — warn and skip rather than break the stream.
          console.warn("Skipping malformed SSE payload:", payload);
        }
      }
    }
  }
}

/** Public surface of {@link useSseChat}. */
export interface UseSseChatResult {
  isStreaming: boolean;
  error: string | null;
  send: (message: string) => Promise<void>;
  stop: () => void;
}

/**
 * Inputs for {@link useSseChat}. Controlled hook — turns and sessionId live in
 * the parent (ChatSessionProvider) so multiple chat threads can share one
 * streaming machine. Switching the current session is a parent-level decision;
 * this hook just reads/writes whichever turns array it's been pointed at.
 */
export interface UseSseChatProps {
  endpoint?: string;
  turns: ChatTurn[];
  setTurns: (updater: (prev: ChatTurn[]) => ChatTurn[]) => void;
  sessionId: string | undefined;
  setSessionId: (id: string | undefined) => void;
}

/**
 * Streams a chat message to the agent and reduces the SSE events into the
 * controlled `turns` array as they arrive.
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
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const send = useCallback(
    async (message: string) => {
      // One stream at a time: a follow-up click or double-submit while a
      // response is streaming would open a second SSE connection and corrupt
      // the turns array. Empty/whitespace-only input is rejected upstream by
      // the prompt component (see data_agent.tsx handleSend), so we don't
      // re-validate the message text here.
      if (isStreaming) return;
      const baseTurn = newTurn(message);
      let turnIndex = -1;
      setTurns((prev) => {
        turnIndex = prev.length;
        return [...prev, baseTurn];
      });
      setIsStreaming(true);
      setError(null);

      // History sent to the agent excludes the current turn. The proxy
      // expects a Gemini-format list (role + parts.text).
      const history = turns.flatMap((turn) => {
        const items: Array<{ role: string; parts: Array<{ text: string }> }> = [
          { role: "user", parts: [{ text: turn.userMessage }] },
        ];
        if (turn.text) {
          items.push({ role: "model", parts: [{ text: turn.text }] });
        }
        return items;
      });

      // Applies a mutation to the in-flight turn, leaving other turns intact.
      const patch = (mutate: (turn: ChatTurn) => ChatTurn) =>
        setTurns((prev) => {
          if (turnIndex < 0 || turnIndex >= prev.length) return prev;
          const next = prev.slice();
          next[turnIndex] = mutate(next[turnIndex]);
          return next;
        });

      try {
        const controller = new AbortController();
        abortRef.current = controller;
        const resp = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            history,
            session_id: sessionId,
          }),
          signal: controller.signal,
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
        if (e instanceof DOMException && e.name === "AbortError") {
          // User clicked Stop — keep whatever partial content arrived and
          // mark the turn as done rather than errored.
          patch((turn) => ({ ...turn, status: "done" }));
        } else {
          const msg = e instanceof Error ? e.message : String(e);
          patch((turn) => ({ ...turn, status: "error", error: msg }));
          setError(msg);
        }
      } finally {
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [endpoint, turns, setTurns, sessionId, setSessionId, isStreaming],
  );

  return { isStreaming, error, send, stop };
}

/**
 * Pure reducer: applies every recognised field of an SSE event to the
 * turn state. The agent sometimes packs multiple fields into one event
 * (e.g. the closing event has both `chart_config` AND `done` — earlier
 * `if … continue` style would silently drop the second field). Every
 * field is independent and additive.
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
    const toolCall: ToolCallEvent = {
      name: evt.name,
      arguments: evt.arguments ?? {},
      status: evt.status === "success" || evt.status === "error" ? evt.status : undefined,
    };
    next = { ...next, toolCalls: [...next.toolCalls, toolCall] };
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

  if (Array.isArray(evt.follow_up_questions)) {
    next = {
      ...next,
      followUps: evt.follow_up_questions,
    };
  }

  const sourceList =
    (Array.isArray(evt.mcp_sources) ? evt.mcp_sources : null) ??
    (Array.isArray(evt.kb_sources) ? evt.kb_sources : null) ??
    (Array.isArray(evt.provenance) ? evt.provenance : null);
  if (sourceList) {
    const seen = new Set(next.provenance.map((item) => item.url));
    const merged = [...next.provenance];
    for (const source of sourceList) {
      if (source && source.url && !seen.has(source.url)) {
        merged.push(source);
        seen.add(source.url);
      }
    }
    next = { ...next, provenance: merged };
  }

  if (evt.done) {
    next = { ...next, status: "done" };
  }

  if (typeof evt.error === "string") {
    next = { ...next, status: "error", error: evt.error };
  }

  return next;
}
