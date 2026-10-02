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

/**
 * Defines the error message shown when the agent rejects the signed
 * conversation history, for example after its signing key changed. Every
 * signature is cleared, so the next question starts without earlier context.
 */
export const TRANSCRIPT_REJECTED_ERROR =
  "The conversation history could not be verified, so earlier context was cleared. Please ask again.";

/** Identifies the HTTP 400 body the agent returns for an unverifiable transcript. */
const TRANSCRIPT_INVALID_REASON = "transcript_invalid";

/**
 * Records the places, variables, and date range of one data query or chart, in
 * the agent's snake_case wire format. The `places`, `parent_place`, and
 * `variables` dicts map each DCID to its display name. It is kept in wire
 * format, rather than mapped to camelCase, because it is covered by the turn's
 * signature and is sent back to the agent unchanged.
 */
export interface QueryScope {
  places: Record<string, string>;
  parent_place: Record<string, string> | null;
  child_place_type: string | null;
  variables: Record<string, string>;
  date_range: [string, string] | null;
}

/** Holds the query scopes (places, variables, and date ranges) from a turn, in wire format. */
export interface ConversationStateSlots {
  scopes: QueryScope[];
}

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
  /** Holds the key sent with the turn's request, which the agent signs into the turn. */
  idempotencyKey?: string;
  /**
   * Counts the conversation's signed turns from 0. Set, with `hmac`, from the
   * terminal event, and cleared when the turn leaves the signed window.
   */
  turnIndex?: number;
  /** Holds the agent's signature over the turn; only signed turns are sent as context. */
  hmac?: string;
  /** Holds the scopes the agent extracted from the turn's tool calls. */
  stateSlots?: ConversationStateSlots;
  /**
   * Holds the agent's summary of the turns compacted out of the window. Only
   * the latest signed turn keeps it, since it covers the whole window.
   */
  compactedSummary?: string | null;
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

/** Identifies one turn of the signed window listed in a `terminal` event. */
interface SignedWindowEntry {
  turn_index: number;
  idempotency_key: string;
  hmac: string;
}

/**
 * Represents the payload of a `terminal` event. An `error` event carries a
 * user-safe `error` message and a machine-readable `reason` (for example,
 * `mcp_timeout`). A `complete` event for a signed turn also carries the
 * turn's `turn_index`, `hmac`, and `state_slots`, the window's
 * `compacted_summary`, and `window`, which lists every turn the next request
 * must send with its current signature.
 */
interface TerminalPayload {
  state: TerminalState;
  error?: string;
  reason?: string;
  idempotency_key: string;
  turn_index?: number;
  hmac?: string;
  state_slots?: ConversationStateSlots;
  compacted_summary?: string | null;
  window?: SignedWindowEntry[];
}

/** Represents the wire format of one signed turn sent back to the agent as context. */
export interface WireTurn {
  turn_index: number;
  idempotency_key: string;
  user_query: string;
  model_response: string;
  state_slots: ConversationStateSlots;
  hmac: string;
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

const newTurn = (userMessage: string, idempotencyKey: string): ChatTurn => ({
  userMessage,
  status: "idle",
  toolCalls: [],
  thoughts: [],
  text: "",
  provenance: [],
  idempotencyKey,
});

/** Represents a turn that carries everything needed to send it back as signed context. */
type SignedTurn = ChatTurn & {
  idempotencyKey: string;
  turnIndex: number;
  hmac: string;
  stateSlots: ConversationStateSlots;
};

/** Reports whether a turn is a completed turn the agent signed. */
function isSignedTurn(turn: ChatTurn): turn is SignedTurn {
  return (
    turn.status === "done" &&
    !turn.stopped &&
    Boolean(turn.hmac) &&
    turn.idempotencyKey !== undefined &&
    turn.turnIndex !== undefined &&
    turn.stateSlots !== undefined
  );
}

/**
 * Builds the transcript fields of a request from the signed turns. The query
 * and answer are sent exactly as stored, because the agent verifies them
 * against the turn's signature.
 */
export function transcriptRequestFields(turns: ChatTurn[]): {
  turns: WireTurn[];
  compacted_summary: string | null;
} {
  const signed = turns.filter(isSignedTurn);
  return {
    turns: signed.map((turn) => ({
      turn_index: turn.turnIndex,
      idempotency_key: turn.idempotencyKey,
      user_query: turn.userMessage,
      model_response: turn.text,
      state_slots: turn.stateSlots,
      hmac: turn.hmac,
    })),
    compacted_summary: signed.at(-1)?.compactedSummary ?? null,
  };
}

/** Returns the turn without its signature, so it is no longer sent as context. */
function withoutSignature(turn: ChatTurn): ChatTurn {
  return turn.hmac === undefined
    ? turn
    : {
        ...turn,
        hmac: undefined,
        turnIndex: undefined,
        compactedSummary: undefined,
      };
}

/**
 * Applies the signed window of a `complete` terminal event to every turn.
 *
 * The turn at `position` receives its signature, state slots, and the
 * window's summary, which every other turn drops so that it is stored once.
 * Compaction re-signs the whole window, so each other signed turn takes the
 * signature the window lists for its idempotency key, and a turn the window
 * no longer lists, because it was compacted into the summary, loses its
 * signature.
 */
export function applySignedWindow(
  turns: ChatTurn[],
  position: number,
  terminal: TerminalPayload,
): ChatTurn[] {
  const { window, hmac, turn_index, state_slots } = terminal;
  if (!window || !hmac || turn_index === undefined || !state_slots) {
    return turns;
  }
  const signatures = new Map(
    window.map((entry) => [entry.idempotency_key, entry]),
  );
  return turns.map((turn, index) => {
    if (index === position) {
      return {
        ...turn,
        turnIndex: turn_index,
        hmac,
        stateSlots: state_slots,
        compactedSummary: terminal.compacted_summary ?? null,
      };
    }
    if (turn.hmac === undefined) return turn;
    const entry =
      turn.idempotencyKey === undefined
        ? undefined
        : signatures.get(turn.idempotencyKey);
    return entry
      ? {
          ...turn,
          hmac: entry.hmac,
          turnIndex: entry.turn_index,
          compactedSummary: undefined,
        }
      : withoutSignature(turn);
  });
}

/** Reports whether an error response is the agent rejecting the transcript. */
async function isTranscriptRejection(resp: Response): Promise<boolean> {
  if (resp.status !== 400) return false;
  try {
    const body: unknown = await resp.json();
    if (typeof body !== "object" || body === null) return false;
    const detail: unknown = (body as { detail?: unknown }).detail;
    return (
      typeof detail === "object" &&
      detail !== null &&
      (detail as { reason?: unknown }).reason === TRANSCRIPT_INVALID_REASON
    );
  } catch {
    return false;
  }
}

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
    // Only `event:` and `data:` lines are used. Other lines, such as `id:`
    // fields and `:` comments, are ignored.
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
      const idempotencyKey = newIdempotencyKey();
      const baseTurn = newTurn(message, idempotencyKey);
      // Holds the in-flight turn's position in the turns array, which differs
      // from its signed `turnIndex` once any earlier turn went unsigned.
      let position = -1;
      setTurns((prev) => {
        position = prev.length;
        return [...prev, baseTurn];
      });
      setIsStreaming(true);
      setError(null);

      // Context sent to the agent excludes the current turn and is limited to
      // the turns the agent signed: a stopped, errored, or unsigned turn is
      // left out, and the agent rejects any change to a signed one.
      const transcript = transcriptRequestFields(turns);

      // Applies a mutation to the in-flight turn, leaving other turns intact.
      const patch = (mutate: (turn: ChatTurn) => ChatTurn) =>
        setTurns((prev) => {
          if (position < 0 || position >= prev.length) return prev;
          const next = prev.slice();
          next[position] = mutate(next[position]);
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
            ...transcript,
            idempotency_key: idempotencyKey,
          }),
          signal: controller.signal,
        });
        if (await isTranscriptRejection(resp)) {
          // The signatures no longer verify, as after a key rotation or an
          // agent restart without a shared key. Clearing them lets the user
          // continue without earlier context instead of failing every turn.
          setTurns((prev) =>
            prev.map((turn, index) =>
              index === position
                ? { ...turn, status: "error", error: TRANSCRIPT_REJECTED_ERROR }
                : withoutSignature(turn),
            ),
          );
          setError(TRANSCRIPT_REJECTED_ERROR);
          return;
        }
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
            const payload = evt.data;
            terminal = payload;
            if (payload.state === "complete") {
              setTurns((prev) => applySignedWindow(prev, position, payload));
            } else {
              setError(terminalError(payload));
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
