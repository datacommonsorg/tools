/**
 * @fileoverview Tests for the SSE chat hook: the typed frame parser, the turn
 * reducer, and the rule that a turn is finished only by a terminal event.
 */

import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  INTERRUPTED_TURN_ERROR,
  applyEvent,
  parseSseStream,
  useSseChat,
  type ChatStreamEvent,
  type ChatTurn,
} from "./use_sse_chat";

const TERMINAL_FIELDS = {
  idempotency_key: "key-1",
  hmac: "",
  state_slots: { scopes: [] },
  compacted_summary: null,
};

/** Encodes one frame the way the agent does: CRLF line endings. */
function frame(event: string, data: unknown, id?: number): string {
  const idLine = id === undefined ? "" : `id: ${id}\r\n`;
  return `${idLine}event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

/** Returns a byte stream that yields each chunk as one read. */
function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

/** Returns a byte stream that yields each chunk, then fails with `failure`. */
function failingStreamOf(
  chunks: string[],
  failure: unknown,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let next = 0;
  return new ReadableStream<Uint8Array>({
    // Enqueue one chunk per pull because calling `controller.error` discards
    // any chunks still queued.
    pull(controller) {
      if (next < chunks.length) {
        controller.enqueue(encoder.encode(chunks[next++]));
      } else {
        controller.error(failure);
      }
    },
  });
}

/** Collects every event the parser yields for the given chunks. */
async function parseAll(chunks: string[]): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = [];
  for await (const event of parseSseStream(streamOf(chunks).getReader())) {
    events.push(event);
  }
  return events;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const blankTurn = (): ChatTurn => ({
  userMessage: "What is the population of France?",
  status: "idle",
  toolCalls: [],
  thoughts: [],
  text: "",
  provenance: [],
});

describe("parseSseStream", () => {
  it("decodes typed frames, including a CRLF split across chunks", async () => {
    // Test: Frame decoding.
    // Situation: Two frames arrive with CRLF endings, the first split
    //   between its CR and LF across two reads.
    // Expectation: Both events are decoded with their names and payloads,
    //   and the split does not produce a spurious empty frame.
    const status = frame("status", { phase: "mcp", message: "Querying" }, 1);
    const text = frame("content", { text: "About 68 million." }, 2);
    const splitAt = status.length - 1;

    const events = await parseAll([
      status.slice(0, splitAt),
      status.slice(splitAt) + text,
    ]);

    expect(events).toEqual([
      { event: "status", data: { phase: "mcp", message: "Querying" } },
      { event: "content", data: { text: "About 68 million." } },
    ]);
  });

  it("decodes frames delivered one character at a time", async () => {
    // Test: Frame decoding when every chunk boundary falls inside a frame.
    // Situation: A frame with bare CR line endings and two CRLF frames
    //   arrive one character per read, so every CR, LF, and blank-line
    //   separator straddles two reads.
    // Expectation: All three events are decoded with their names and
    //   payloads, and no spurious frames are produced.
    const status = `event: status\rdata: ${JSON.stringify({ phase: "mcp" })}\r\r`;
    const text = frame("content", { text: "About 68 million." }, 2);
    const complete = { state: "complete", ...TERMINAL_FIELDS };
    const terminal = frame("terminal", complete, 3);

    const events = await parseAll([...(status + text + terminal)]);

    expect(events).toEqual([
      { event: "status", data: { phase: "mcp" } },
      { event: "content", data: { text: "About 68 million." } },
      { event: "terminal", data: complete },
    ]);
  });

  it("skips comments, unknown events, untyped frames, and bad JSON", async () => {
    // Test: Tolerance of frames the UI does not understand.
    // Situation: The stream carries a comment, an unknown event name, an
    //   untyped `data:` frame, a frame with malformed JSON, frames whose
    //   JSON is null, a string, or an array, and a heartbeat.
    // Expectation: Only the heartbeat is yielded; the rest are skipped
    //   without ending the stream.
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const events = await parseAll([
      ": ping\r\n\r\n",
      frame("usage", { total: 1 }),
      'data: {"text": "untyped"}\r\n\r\n',
      "event: content\r\ndata: {not json\r\n\r\n",
      frame("content", null),
      frame("content", "About 68 million."),
      frame("terminal", ["complete"]),
      frame("heartbeat", {}),
    ]);

    expect(events).toEqual([{ event: "heartbeat", data: {} }]);
  });

  it("cancels and releases the stream when the caller stops early", async () => {
    // Test: Cleanup when iteration ends before the stream does.
    // Situation: The stream holds two frames and stays open, and the caller
    //   breaks out of the loop after the first event.
    // Expectation: The stream is canceled, so the response stops
    //   downloading, and it is no longer locked to the reader.
    const encoder = new TextEncoder();
    let canceled = false;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(frame("status", { phase: "mcp" })));
        controller.enqueue(encoder.encode(frame("content", { text: "x" })));
      },
      cancel() {
        canceled = true;
      },
    });

    for await (const event of parseSseStream(stream.getReader())) {
      expect(event.event).toBe("status");
      break;
    }

    expect(canceled).toBe(true);
    expect(stream.locked).toBe(false);
  });

  it("releases the stream and keeps the original error when a read fails", async () => {
    // Test: Cleanup when the stream fails.
    // Situation: The stream fails with a network error before any frame
    //   arrives.
    // Expectation: The parser rejects with that network error, not with an
    //   error from the cleanup, and the stream is no longer locked.
    const stream = failingStreamOf([], new TypeError("network error"));

    const consume = async () => {
      for await (const _event of parseSseStream(stream.getReader())) {
        // The stream yields no events.
      }
    };

    await expect(consume()).rejects.toThrow("network error");
    expect(stream.locked).toBe(false);
  });
});

describe("applyEvent", () => {
  it("builds the turn from status, thought, and content events", () => {
    // Test: Reduction of the non-terminal events.
    // Situation: A turn receives a status, a thought, two text chunks,
    //   duplicate sources, a truncation flag, and a chart config.
    // Expectation: The status matches the phase, the text chunks are
    //   concatenated, duplicate source URLs are removed, truncation is set,
    //   and the chart config is mapped to camelCase.
    const events: ChatStreamEvent[] = [
      { event: "status", data: { phase: "synthesis" } },
      { event: "thought", data: { thought: "Checking", phase: "mcp" } },
      { event: "content", data: { text: "About " } },
      { event: "content", data: { text: "68 million." } },
      {
        event: "content",
        data: {
          sources: [
            { name: "INSEE", url: "https://insee.fr/" },
            { name: "INSEE again", url: "https://insee.fr/" },
          ],
        },
      },
      { event: "content", data: { data_status: { truncated: true } } },
      {
        event: "content",
        data: { chart_config: { should_render: true, hide_charts: true } },
      },
    ];

    const turn = events.reduce(applyEvent, blankTurn());

    expect(turn.status).toBe("synthesis");
    expect(turn.thoughts).toEqual([{ text: "Checking", phase: "mcp" }]);
    expect(turn.text).toBe("About 68 million.");
    expect(turn.provenance).toEqual([{ name: "INSEE", url: "https://insee.fr/" }]);
    expect(turn.truncated).toBe(true);
    expect(turn.chartConfig).toEqual({
      shouldRender: true,
      hideCharts: true,
      charts: undefined,
    });
  });

  it.each([
    ["complete", undefined, "done", undefined],
    ["error", "The data request failed.", "error", "The data request failed."],
    ["refused", undefined, "error", "The request was declined."],
  ] as const)(
    "maps a %s terminal event onto the turn status",
    (state, error, status, shownError) => {
      // Test: Terminal state mapping.
      // Situation: A turn receives a terminal event in the given state.
      // Expectation: `complete` finishes the turn; other states make it an
      //   error turn carrying the server's message or a default one.
      const turn = applyEvent(blankTurn(), {
        event: "terminal",
        data: { state, error, ...TERMINAL_FIELDS },
      });

      expect(turn.status).toBe(status);
      expect(turn.error).toBe(shownError);
    },
  );
});

describe("useSseChat", () => {
  /** Renders the hook over local turn state and stubs fetch with the body. */
  function renderChat(body: string[] | ReadableStream<Uint8Array>) {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      body: Array.isArray(body) ? streamOf(body) : body,
    });
    vi.stubGlobal("fetch", fetchMock);
    const view = renderHook(() => {
      const [turns, setTurns] = useState<ChatTurn[]>([]);
      return { turns, chat: useSseChat({ turns, setTurns }) };
    });
    return { ...view, fetchMock };
  }

  it("marks a stream that ends without a terminal event as interrupted", async () => {
    // Test: EOF without a terminal event.
    // Situation: The stream delivers a status event and partial text, and
    //   then ends without a terminal event.
    // Expectation: The turn keeps its partial text but ends as an error
    //   with the interrupted-connection message, not stuck mid-stream.
    const { result } = renderChat([
      frame("status", { phase: "synthesis" }, 1),
      frame("content", { text: "About 68" }, 2),
    ]);

    await act(() => result.current.chat.send("What is the population of France?"));

    const [turn] = result.current.turns;
    expect(turn.text).toBe("About 68");
    expect(turn.status).toBe("error");
    expect(turn.error).toBe(INTERRUPTED_TURN_ERROR);
    expect(result.current.chat.error).toBe(INTERRUPTED_TURN_ERROR);
  });

  it("finishes the turn on its terminal event and sends an idempotency key", async () => {
    // Test: A complete stream.
    // Situation: The stream delivers text, a complete terminal event, and
    //   follow-ups after it.
    // Expectation: The turn is done with its follow-ups, no error is set,
    //   and the request carried a non-empty idempotency key.
    const { result, fetchMock } = renderChat([
      frame("content", { text: "About 68 million." }, 1),
      frame("terminal", { state: "complete", ...TERMINAL_FIELDS }, 2),
      frame("follow_ups", { follow_up_questions: ["And Spain?"] }, 3),
    ]);

    await act(() => result.current.chat.send("What is the population of France?"));

    const [turn] = result.current.turns;
    expect(turn.status).toBe("done");
    expect(turn.followUps).toEqual(["And Spain?"]);
    expect(result.current.chat.error).toBeNull();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(typeof body.idempotency_key).toBe("string");
    expect(body.idempotency_key).not.toBe("");
    expect(body).not.toHaveProperty("session_id");
  });

  it("reports a stream that fails mid-turn as interrupted", async () => {
    // Test: A connection lost after the response started.
    // Situation: The stream delivers some text, then fails with the
    //   browser's network error.
    // Expectation: The turn ends as an error with the interrupted-connection
    //   message rather than the browser's wording.
    const { result } = renderChat(
      failingStreamOf(
        [frame("content", { text: "About 68" }, 1)],
        new TypeError("network error"),
      ),
    );

    await act(() => result.current.chat.send("What is the population of France?"));

    const [turn] = result.current.turns;
    expect(turn.status).toBe("error");
    expect(turn.error).toBe(INTERRUPTED_TURN_ERROR);
    expect(result.current.chat.error).toBe(INTERRUPTED_TURN_ERROR);
  });

  it("keeps a completed turn complete when Stop lands during follow-ups", async () => {
    // Test: An abort after the terminal event.
    // Situation: The stream delivers the answer and a complete terminal
    //   event, and then fails with an `AbortError` as when the user clicks
    //   Stop while follow-ups are streaming.
    // Expectation: The turn stays done, is not flagged stopped, and carries
    //   no error.
    const { result } = renderChat(
      failingStreamOf(
        [
          frame("content", { text: "About 68 million." }, 1),
          frame("terminal", { state: "complete", ...TERMINAL_FIELDS }, 2),
        ],
        new DOMException("The operation was aborted.", "AbortError"),
      ),
    );

    await act(() => result.current.chat.send("What is the population of France?"));

    const [turn] = result.current.turns;
    expect(turn.status).toBe("done");
    expect(turn.stopped).toBeUndefined();
    expect(turn.error).toBeUndefined();
    expect(result.current.chat.error).toBeNull();
  });
});
