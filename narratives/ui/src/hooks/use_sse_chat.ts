/**
 * @fileoverview Provides the SSE chat hook: streams agent responses and reduces events into chat turns.
 */

import { useCallback, useRef, useState } from "react";

/** SSE framing: events are separated by a blank line (after line-ending normalization). */
const SSE_EVENT_SEPARATOR = "\n\n";
/** SSE framing: the event name line is prefixed with `event:`. */
const SSE_EVENT_NAME_PREFIX = "event:";
/** SSE framing: payload lines are prefixed with `data:`. */
const SSE_EVENT_DATA_PREFIX = "data:";
/** Specifies the base-36 radix used for the random suffix of a fallback idempotency key. */
const FALLBACK_KEY_RADIX = 36;
/** Specifies how many random characters are kept after the leading "0." in a fallback idempotency key. */
const FALLBACK_KEY_RANDOM_CHARS = 8;

/**
 * Represents a tool invocation emitted by the `/agent/chat/stream` endpoint.
 * Mirrors the tool-call records that `workflows/mcp_loop.py` builds.
 */
export interface ToolCallEvent {
  name: string;
  arguments: Record<string, unknown>;
  status?: "success" | "error";
  /**
   * The tool's raw response, as the MCP server returned it. The agent has
   * always sent this and the reducer used to discard it; it is kept now because
   * it is the only place the facet-to-provenance mapping exists, which is what
   * makes "which source did this answer actually use" answerable in the UI.
   * Untruncated by design, so it can be large.
   */
  result?: string;
}

/** A reasoning snippet emitted while the agent works, tagged by pipeline phase. */
export interface ThoughtEvent {
  text: string;
  phase: "mcp" | "synthesis";
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
 * (the agent's `gemini/schemas.py` CHART_CONFIG_SCHEMA + homepage.html
 * renderDCComponent).
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
 * normalizes both shapes.
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
export interface ProvenanceItem {
  name: string;
  url: string;
  /**
   * License terms, e.g. "Creative Commons Attribution License". Only
   * get_variable_metadata reports this; observation calls yield a bare URL.
   */
  license?: string;
}

/** Represents the lifecycle of one chat turn, driven by `status` and `terminal` events. */
export type TurnStatus =
  | "idle"
  | "mcp"
  | "synthesis"
  | "done"
  | "error";

/**
 * Defines the error message shown when a turn's stream ends without a
 * terminal event because the connection dropped or the page closed mid-stream.
 */
export const INTERRUPTED_TURN_ERROR =
  "The connection was interrupted before the response finished.";

/** Accumulated UI state for one user message and its streamed response. */
export interface ChatTurn {
  userMessage: string;
  status: TurnStatus;
  toolCalls: ToolCallEvent[];
  thoughts: ThoughtEvent[];
  text: string;
  chartConfig?: ChartConfig;
  provenance: ProvenanceItem[];
  /** Holds self-contained follow-up questions emitted by the agent after the terminal event. */
  followUps?: string[];
  error?: string;
  /**
   * Set when the user aborts the turn via Stop. Drives the "Stopped per your
   * request" note in place of the (now-irrelevant) reasoning/answer chrome.
   */
  stopped?: boolean;
  /**
   * Set when the agent ran out of research steps before it was finished, so the
   * answer is built on less data than it meant to gather. Not an error: the
   * answer still arrives with citations and charts, which is exactly why it
   * needs saying out loud.
   */
  truncated?: boolean;
}

/** Identifies the terminal state of a turn as reported by its `terminal` event. */
type TerminalState = "complete" | "error" | "refused" | "canceled";

/**
 * Represents the payload of a `content` event, which carries one content field
 * per frame.
 */
interface ContentPayload {
  text?: string;
  tool_call?: ToolCallEvent;
  sources?: ProvenanceItem[];
  /**
   * Reports the completeness of the data behind the answer; `truncated` is
   * the flag the UI acts on.
   */
  data_status?: { truncated?: boolean; has_data?: boolean };
  chart_config?: RawChartConfig;
}

/**
 * Represents the payload of a `terminal` event. An `error` event carries a
 * user-safe `error` message and a machine-readable `reason` (for example,
 * `mcp_timeout`). `hmac`, `state_slots`, and `compacted_summary` are
 * placeholders until the agent signs transcripts.
 */
interface TerminalPayload {
  state: TerminalState;
  error?: string;
  reason?: string;
  idempotency_key: string;
  hmac: string;
  state_slots: { scopes: unknown[] };
  compacted_summary: string | null;
}

/** Represents one decoded event from `/agent/chat/stream`, discriminated by its `event:` name. */
export type ChatStreamEvent =
  | {
      event: "status";
      data: { phase: "mcp" | "synthesis" | "chart_config"; message?: string };
    }
  | { event: "thought"; data: { thought: string; phase?: ThoughtEvent["phase"] } }
  | { event: "content"; data: ContentPayload }
  | { event: "terminal"; data: TerminalPayload }
  | { event: "follow_ups"; data: { follow_up_questions: string[] } }
  | { event: "heartbeat"; data: Record<string, never> };

const CHAT_STREAM_EVENTS: ReadonlySet<string> = new Set<ChatStreamEvent["event"]>([
  "status",
  "thought",
  "content",
  "terminal",
  "follow_ups",
  "heartbeat",
]);

const newTurn = (userMessage: string): ChatTurn => ({
  userMessage,
  status: "idle",
  toolCalls: [],
  thoughts: [],
  text: "",
  provenance: [],
});

/** Returns a fresh idempotency key for one submission. */
function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // `crypto.randomUUID` exists only in secure contexts (HTTPS or localhost),
  // so a deployment served over plain HTTP lands here, as do old browsers.
  const random = Math.random()
    .toString(FALLBACK_KEY_RADIX)
    .slice(2, 2 + FALLBACK_KEY_RANDOM_CHARS);
  return `k_${Date.now()}_${random}`;
}

/**
 * Decodes one SSE frame (the lines between two blank lines). Returns null for
 * frames that carry no known event, such as comments, unknown event names,
 * malformed JSON, or JSON values that are not objects, so the caller can skip
 * them without interrupting the stream.
 */
function decodeFrame(frame: string): ChatStreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    // Lines starting with ":" are comments; `id:` lines are not needed here.
    if (line.startsWith(SSE_EVENT_NAME_PREFIX)) {
      event = line.slice(SSE_EVENT_NAME_PREFIX.length).trim();
    } else if (line.startsWith(SSE_EVENT_DATA_PREFIX)) {
      dataLines.push(line.slice(SSE_EVENT_DATA_PREFIX.length).trimStart());
    }
  }
  if (!CHAT_STREAM_EVENTS.has(event) || dataLines.length === 0) return null;
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    data = undefined;
  }
  // Every event's payload is an object; the reducer reads fields off it.
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    console.warn("Skipping malformed SSE payload:", dataLines.join("\n"));
    return null;
  }
  return { event, data } as ChatStreamEvent;
}

/** Converts CRLF and CR line endings to LF. */
function normalizeLineEndings(text: string): string {
  return text.replace(/\r\n?/g, "\n");
}

/**
 * Parses the SSE byte stream into typed events.
 *
 * Normalizes CRLF and CR line endings (the agent sends CRLF), splits on the
 * blank-line frame boundary, and decodes each frame's `event:` name and
 * `data:` payload.
 *
 * Each chunk is normalized and searched for frame boundaries once, when it
 * arrives, so the work done stays proportional to the size of the stream. A
 * `tool_call` frame carries a full MCP result and can span many chunks;
 * rescanning the whole buffer on every chunk would make parsing it
 * quadratic.
 */
export async function* parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<ChatStreamEvent, void, unknown> {
  const decoder = new TextDecoder();
  let buffer = "";
  // Set when a chunk ends in CR, which is held back until the next chunk
  // shows whether it is the first half of a CRLF pair.
  let pendingCr = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      let chunk = decoder.decode(value, { stream: true });
      if (pendingCr) chunk = "\r" + chunk;
      pendingCr = chunk.endsWith("\r");
      if (pendingCr) chunk = chunk.slice(0, -1);
      // A separator that straddles the previous chunk and this one starts in
      // the last character of the existing buffer, so the search starts
      // there.
      let searchFrom = Math.max(
        0,
        buffer.length - (SSE_EVENT_SEPARATOR.length - 1),
      );
      buffer += normalizeLineEndings(chunk);
      let idx;
      while ((idx = buffer.indexOf(SSE_EVENT_SEPARATOR, searchFrom)) >= 0) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + SSE_EVENT_SEPARATOR.length);
        searchFrom = 0;
        const event = decodeFrame(frame);
        if (event) yield event;
      }
    }
  } finally {
    // This block runs even when the caller stops reading early. It cancels
    // the download and releases the stream. If the stream has already
    // failed, `cancel` returns a rejected promise, which is ignored.
    await reader.cancel().catch(() => {});
    reader.releaseLock();
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
 * Configures {@link useSseChat}. This is a controlled hook: turns live in the
 * parent (`ChatSessionProvider`) so multiple chat threads can share one
 * streaming machine. Switching the current session is a parent-level decision;
 * this hook reads and writes whichever turns array it is given.
 */
export interface UseSseChatProps {
  endpoint?: string;
  turns: ChatTurn[];
  setTurns: (updater: (prev: ChatTurn[]) => ChatTurn[]) => void;
}

/**
 * Streams a chat message to the agent and reduces the SSE events into the
 * controlled `turns` array as they arrive.
 */
export function useSseChat(props: UseSseChatProps): UseSseChatResult {
  const { endpoint = "/agent/chat/stream", turns, setTurns } = props;
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
      // expects a Gemini-format list of strictly alternating user/model roles.
      // Only completed turns that produced model text are included: a stopped
      // or errored turn (especially one aborted before any text arrived) would
      // otherwise emit a lone `user` entry, producing consecutive `user`
      // messages that Gemini rejects with a 400.
      const history = turns
        .filter((turn) => !turn.stopped && turn.status === "done" && turn.text)
        .flatMap((turn) => [
          { role: "user", parts: [{ text: turn.userMessage }] },
          { role: "model", parts: [{ text: turn.text }] },
        ]);

      // Applies a mutation to the in-flight turn, leaving other turns intact.
      const patch = (mutate: (turn: ChatTurn) => ChatTurn) =>
        setTurns((prev) => {
          if (turnIndex < 0 || turnIndex >= prev.length) return prev;
          const next = prev.slice();
          next[turnIndex] = mutate(next[turnIndex]);
          return next;
        });

      // Holds the terminal event payload once it arrives. If an error or abort
      // occurs after that point while follow-up questions are streaming, the
      // turn keeps the state set by its terminal event.
      let terminal: TerminalPayload | null = null;
      // Tracks whether the HTTP response headers have arrived. Any network
      // error after this point is reported as an interrupted stream.
      let streamStarted = false;
      try {
        const controller = new AbortController();
        abortRef.current = controller;
        const resp = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            history,
            idempotency_key: newIdempotencyKey(),
          }),
          signal: controller.signal,
        });
        if (!resp.ok || !resp.body) {
          const errText = `HTTP ${resp.status} ${resp.statusText}`;
          patch((turn) => ({ ...turn, status: "error", error: errText }));
          setError(errText);
          return;
        }

        streamStarted = true;
        const reader = resp.body.getReader();
        for await (const evt of parseSseStream(reader)) {
          // Heartbeat frames carry no state changes, so skipping them avoids
          // an unnecessary re-render.
          if (evt.event === "heartbeat") continue;
          patch((turn) => applyEvent(turn, evt));
          if (evt.event === "terminal") {
            terminal = evt.data;
            if (evt.data.state !== "complete") {
              setError(terminalError(evt.data));
            }
          }
        }
        // A turn is finished only once its terminal event arrives. A stream
        // that ends without one was cut off, however much text it delivered.
        if (!terminal) {
          patch((turn) => ({
            ...turn,
            status: "error",
            error: INTERRUPTED_TURN_ERROR,
          }));
          setError(INTERRUPTED_TURN_ERROR);
        }
      } catch (e) {
        if (terminal) {
          // The turn already ended; only the follow-ups were cut off, and
          // the turn keeps the state its terminal event gave it.
          return;
        }
        if (e instanceof DOMException && e.name === "AbortError") {
          // User clicked Stop — mark the turn done and flag it stopped so the
          // UI shows a clear "Stopped per your request" note instead of the
          // half-finished reasoning/answer.
          patch((turn) => ({ ...turn, status: "done", stopped: true }));
        } else {
          // Before the response starts, report the browser's fetch error; once
          // the stream has started, report the fixed interrupted-stream error
          // because browser stream error messages vary across engines.
          const msg = streamStarted
            ? INTERRUPTED_TURN_ERROR
            : e instanceof Error
              ? e.message
              : String(e);
          patch((turn) => ({ ...turn, status: "error", error: msg }));
          setError(msg);
        }
      } finally {
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [endpoint, turns, setTurns, isStreaming],
  );

  return { isStreaming, error, send, stop };
}

/** Returns the message shown for a terminal event that is not `complete`. */
function terminalError(terminal: TerminalPayload): string {
  if (terminal.error) return terminal.error;
  if (terminal.state === "refused") return "The request was declined.";
  if (terminal.state === "canceled") {
    return "The response was canceled before it finished.";
  }
  return "The response failed. Please try again.";
}

/** Applies one `content` payload to the turn state. */
function applyContent(turn: ChatTurn, content: ContentPayload): ChatTurn {
  let next = turn;
  if (typeof content.text === "string") {
    next = { ...next, text: next.text + content.text };
  }
  if (content.tool_call) {
    next = { ...next, toolCalls: [...next.toolCalls, content.tool_call] };
  }
  if (Array.isArray(content.sources)) {
    const seen = new Set(next.provenance.map((item) => item.url));
    const merged = [...next.provenance];
    for (const source of content.sources) {
      if (source && source.url && !seen.has(source.url)) {
        merged.push(source);
        seen.add(source.url);
      }
    }
    next = { ...next, provenance: merged };
  }
  // Sticky: once a turn is known to be truncated it stays truncated, so a later
  // event without data_status cannot quietly clear the warning.
  if (content.data_status?.truncated) {
    next = { ...next, truncated: true };
  }
  if (content.chart_config) {
    next = { ...next, chartConfig: mapRawChartConfig(content.chart_config) };
  }
  return next;
}

/** Applies one typed SSE event to the turn state. */
export function applyEvent(turn: ChatTurn, evt: ChatStreamEvent): ChatTurn {
  switch (evt.event) {
    case "status":
      if (evt.data.phase === "mcp" || evt.data.phase === "synthesis") {
        return { ...turn, status: evt.data.phase };
      }
      return turn;
    case "thought":
      return {
        ...turn,
        thoughts: [
          ...turn.thoughts,
          { text: evt.data.thought, phase: evt.data.phase ?? "synthesis" },
        ],
      };
    case "content":
      return applyContent(turn, evt.data);
    case "terminal":
      return evt.data.state === "complete"
        ? { ...turn, status: "done" }
        : { ...turn, status: "error", error: terminalError(evt.data) };
    case "follow_ups":
      return Array.isArray(evt.data.follow_up_questions)
        ? { ...turn, followUps: evt.data.follow_up_questions }
        : turn;
    case "heartbeat":
      return turn;
  }
}
