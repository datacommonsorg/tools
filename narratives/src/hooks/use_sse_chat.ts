import { useCallback, useState } from "react";

// Event types emitted by the agent sidecar's /agent/chat/stream endpoint.
// Mirrors what mcp_proxy_only.py's chat_stream() generator produces.

export type ToolCallEvent = {
  name: string;
  arguments: Record<string, unknown>;
  status?: "success" | "error";
};

export type ThoughtEvent = {
  text: string;
  phase: "mcp" | "kb" | "synthesis";
};

// Mirrors the upstream VM payload (mcp_proxy_only.py CHART_CONFIG_SCHEMA +
// homepage.html renderDCComponent). Supports the modern multi-chart format
// (`charts: [...]`) and the legacy single-chart fallback (variable_dcids at
// the top level).
export type ChartItem = {
  viz_type:
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
  variable_dcids: string[];
  place_dcids?: string[];
  parent_place?: string;
  child_place_type?: string;
  date?: string;
  unit?: string;
};

export type ChartConfig = {
  should_render: boolean;
  hide_charts?: boolean;
  charts?: ChartItem[];
  // Legacy single-chart fallback fields (older agent versions emit these
  // alongside `should_render` instead of inside a `charts` array).
  viz_type?: ChartItem["viz_type"];
  title?: string;
  variable_dcids?: string[];
  place_dcids?: string[];
  parent_place?: string;
  child_place_type?: string;
  date?: string;
};

export type ProvenanceItem = { name: string; url: string };

export type TurnStatus =
  | "idle"
  | "mcp"
  | "kb"
  | "synthesis"
  | "done"
  | "error";

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

const newTurn = (userMessage: string): ChatTurn => ({
  userMessage,
  status: "idle",
  toolCalls: [],
  thoughts: [],
  text: "",
  provenance: [],
});

// Stream parser: splits the SSE chunks on the blank-line boundary, then on
// each event extracts the `data:` payload as JSON. The Python proxy always
// emits a single `data: {json}\n\n` per event, so we don't worry about
// multi-line data payloads.
async function* parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<Record<string, unknown>, void, unknown> {
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const rawEvent = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of rawEvent.split("\n")) {
        if (!line.startsWith("data:")) {
          continue;
        }
        const payload = line.slice(5).trim();
        if (!payload) {
          continue;
        }
        try {
          yield JSON.parse(payload);
        } catch {
          // Malformed JSON — skip rather than break the stream.
        }
      }
    }
  }
}

export interface UseSseChatResult {
  isStreaming: boolean;
  error: string | null;
  send: (message: string) => Promise<void>;
}

// Controlled hook — turns and sessionId live in the parent (ChatSessionProvider)
// so multiple chat threads can share one streaming machine. Switching the
// current session is a parent-level decision; this hook just reads/writes
// whichever turns array it's been pointed at.
export interface UseSseChatProps {
  endpoint?: string;
  turns: ChatTurn[];
  setTurns: (updater: (prev: ChatTurn[]) => ChatTurn[]) => void;
  sessionId: string | undefined;
  setSessionId: (id: string | undefined) => void;
}

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

      // History sent to the agent excludes the current turn. The proxy
      // expects a Gemini-format list (role + parts.text).
      const history = turns.flatMap((t) => {
        const items: Array<{ role: string; parts: Array<{ text: string }> }> = [
          { role: "user", parts: [{ text: t.userMessage }] },
        ];
        if (t.text) {
          items.push({ role: "model", parts: [{ text: t.text }] });
        }
        return items;
      });

      const patch = (mut: (t: ChatTurn) => ChatTurn) =>
        setTurns((prev) => {
          if (turnIndex < 0 || turnIndex >= prev.length) {
            return prev;
          }
          const next = prev.slice();
          next[turnIndex] = mut(next[turnIndex]);
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
          patch((t) => ({ ...t, status: "error", error: errText }));
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
          patch((t) => applyEvent(t, evt));
          if (typeof evt.error === "string") {
            setError(evt.error);
          }
          if (typeof evt.session_id === "string") {
            setSessionId(evt.session_id);
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        patch((t) => ({ ...t, status: "error", error: msg }));
        setError(msg);
      } finally {
        setIsStreaming(false);
      }
    },
    [endpoint, turns, setTurns, sessionId, setSessionId],
  );

  return { isStreaming, error, send };
}

// Pure reducer: applies every recognised field of an SSE event to the
// turn state. The agent sometimes packs multiple fields into one event
// (e.g. the closing event has both `chart_config` AND `done` — earlier
// `if … continue` style would silently drop the second field). Every
// field is independent and additive.
function applyEvent(t: ChatTurn, evt: Record<string, unknown>): ChatTurn {
  let next = t;

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
      toolCalls: [...next.toolCalls, evt.tool_call as ToolCallEvent],
    };
  }
  // Some agent versions also emit the tool result inline as its own field.
  if ((evt as { name?: string; arguments?: unknown }).name && (evt as { type?: string }).type === "tool_call") {
    const tc: ToolCallEvent = {
      name: (evt as { name: string }).name,
      arguments: ((evt as { arguments?: Record<string, unknown> }).arguments) ?? {},
      status: (evt as { status?: "success" | "error" }).status,
    };
    next = { ...next, toolCalls: [...next.toolCalls, tc] };
  }

  if (typeof evt.thought === "string") {
    const phase = (evt.phase as ThoughtEvent["phase"]) ?? "synthesis";
    next = {
      ...next,
      thoughts: [...next.thoughts, { text: evt.thought, phase }],
    };
  }

  if (typeof evt.text === "string") {
    next = { ...next, text: next.text + (evt.text as string) };
  }

  if (evt.chart_config) {
    next = { ...next, chartConfig: evt.chart_config as ChartConfig };
  }

  const sourceList =
    (Array.isArray((evt as { mcp_sources?: unknown }).mcp_sources)
      ? (evt as { mcp_sources: ProvenanceItem[] }).mcp_sources
      : null) ??
    (Array.isArray((evt as { kb_sources?: unknown }).kb_sources)
      ? (evt as { kb_sources: ProvenanceItem[] }).kb_sources
      : null) ??
    (Array.isArray((evt as { provenance?: unknown }).provenance)
      ? (evt as { provenance: ProvenanceItem[] }).provenance
      : null);
  if (sourceList) {
    const seen = new Set(next.provenance.map((p) => p.url));
    const merged = [...next.provenance];
    for (const s of sourceList) {
      if (s && s.url && !seen.has(s.url)) {
        merged.push(s);
        seen.add(s.url);
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
