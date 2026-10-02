/**
 * @fileoverview Tests for the SSE chat hook: the typed frame parser, the turn
 * reducer, the rule that a turn is finished only by a terminal event, and the
 * signed transcript the hook stores and sends back.
 */

import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  INTERRUPTED_TURN_ERROR,
  TRANSCRIPT_REJECTED_ERROR,
  applyEvent,
  applySignedWindow,
  parseSseStream,
  transcriptRequestFields,
  useSseChat,
  type ChatStreamEvent,
  type ChatTurn,
  type ConversationStateSlots,
  type WireTurn,
} from "./use_sse_chat";

/** Represents the JSON body that the hook posts to the agent. */
interface WireRequest {
  message: string;
  idempotency_key: string;
  turns: WireTurn[];
  compacted_summary: string | null;
}

/** Parses a posted body once into its declared shape. */
function parseRequest(body: unknown): WireRequest {
  return JSON.parse(String(body)) as WireRequest;
}

const TERMINAL_FIELDS = { idempotency_key: "key-1" };

const SLOTS: ConversationStateSlots = {
  scopes: [
    {
      places: { "country/FRA": "France" },
      parent_place: null,
      child_place_type: null,
      variables: { Count_Person: "Total Population" },
      date_range: ["2023", "2023"],
    },
  ],
};

/** Returns a 64-character hex signature made of one repeated digit. */
const sig = (digit: string): string => digit.repeat(64);

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

/** Returns a completed turn the agent signed at the given index. */
const signedTurn = (
  index: number,
  overrides: Partial<ChatTurn> = {},
): ChatTurn => ({
  ...blankTurn(),
  userMessage: `Question ${index}`,
  text: `Answer ${index}`,
  status: "done",
  idempotencyKey: `key-${index}`,
  turnIndex: index,
  hmac: sig(String(index)),
  stateSlots: SLOTS,
  compactedSummary: null,
  ...overrides,
});

describe("transcriptRequestFields", () => {
  it("sends only signed turns, verbatim, with the latest summary", () => {
    // Test: Verify the selection and wire mapping of context turns.
    // Situation: Two signed turns (the second under a summary) are mixed with
    //   an error turn, a stopped turn, and an unsigned complete turn.
    // Expectation: Only the signed turns are sent, in order, with the query,
    //   answer, and state slots exactly as stored, and the summary comes from
    //   the last signed turn.
    const turns: ChatTurn[] = [
      signedTurn(0),
      { ...blankTurn(), status: "error", error: "failed" },
      signedTurn(1, { compactedSummary: "Earlier turns." }),
      { ...signedTurn(2), stopped: true },
      { ...blankTurn(), status: "done", text: "Unsigned answer" },
    ];

    expect(transcriptRequestFields(turns)).toEqual({
      turns: [0, 1].map((index) => ({
        turn_index: index,
        idempotency_key: `key-${index}`,
        user_query: `Question ${index}`,
        model_response: `Answer ${index}`,
        state_slots: SLOTS,
        hmac: sig(String(index)),
      })),
      compacted_summary: "Earlier turns.",
    });
  });

  it("sends an empty window when no turn is signed", () => {
    // Test: Verify the request fields for the first turn of a conversation.
    // Situation: The turn list is empty.
    // Expectation: Both the turns list and the compacted summary are empty.
    expect(transcriptRequestFields([])).toEqual({
      turns: [],
      compacted_summary: null,
    });
  });
});

describe("applySignedWindow", () => {
  it("re-signs retained turns and unsigns compacted ones", () => {
    // Test: Verify that applying a signed window updates turns after
    //   compaction.
    // Situation: Two signed turns and an in-flight turn exist, and the
    //   terminal event's window drops turn 0 and re-signs turn 1 under a new
    //   summary.
    // Expectation: Turn 0 loses its signature, turn 1 takes the new one and
    //   drops its stored summary, and the in-flight turn receives its index,
    //   signature, slots, and the summary.
    const turns = [signedTurn(0), signedTurn(1), blankTurn()];

    const next = applySignedWindow(turns, 2, {
      state: "complete",
      idempotency_key: "key-2",
      turn_index: 2,
      hmac: sig("c"),
      state_slots: SLOTS,
      compacted_summary: "Turn 0 summary.",
      window: [
        { turn_index: 1, idempotency_key: "key-1", hmac: sig("b") },
        { turn_index: 2, idempotency_key: "key-2", hmac: sig("c") },
      ],
    });

    expect(next[0].hmac).toBeUndefined();
    expect(next[0].turnIndex).toBeUndefined();
    expect(next[1].hmac).toBe(sig("b"));
    expect(next[1].compactedSummary).toBeUndefined();
    expect(next[2]).toMatchObject({
      turnIndex: 2,
      hmac: sig("c"),
      stateSlots: SLOTS,
      compactedSummary: "Turn 0 summary.",
    });
  });

  it("leaves the turns unchanged for an unsigned complete event", () => {
    // Test: Verify that an unsigned complete terminal event leaves the turns
    //   unchanged.
    // Situation: The agent did not sign the turn because its answer was too
    //   long.
    // Expectation: No turn changes, so earlier signed turns remain context.
    const turns = [signedTurn(0), blankTurn()];

    expect(
      applySignedWindow(turns, 1, { state: "complete", idempotency_key: "k" }),
    ).toBe(turns);
  });
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
  function renderChat(
    body: string[] | ReadableStream<Uint8Array>,
    initialTurns: ChatTurn[] = [],
  ) {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      body: Array.isArray(body) ? streamOf(body) : body,
    });
    vi.stubGlobal("fetch", fetchMock);
    const view = renderHook(() => {
      const [turns, setTurns] = useState<ChatTurn[]>(initialTurns);
      return { turns, chat: useSseChat({ turns, setTurns }) };
    });
    return { ...view, fetchMock };
  }

  /** Returns the parsed JSON body of the fetch call at `index`. */
  function requestBody(
    fetchMock: ReturnType<typeof vi.fn>,
    index: number,
  ): WireRequest {
    const init = fetchMock.mock.calls[index][1] as RequestInit;
    return parseRequest(init.body);
  }

  it("stores the signed turn and sends it back with the next request", async () => {
    // Test: The signed transcript round-trips across turns.
    // Situation: The first turn completes with a signed terminal event, and
    //   the user asks a follow-up.
    // Expectation: The turn stores its key, index, signature, and slots, and
    //   the follow-up request carries it verbatim with the summary and no
    //   `history` field.
    const { result, fetchMock } = renderChat([]);
    // Signs each request's turn the way the agent does: the window lists the
    // turns the request carried, then the new turn under the request's key.
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) => {
      const request = parseRequest(init.body);
      const index = request.turns.length;
      const entry = {
        turn_index: index,
        idempotency_key: request.idempotency_key,
        hmac: sig(String(index)),
      };
      const window = [
        ...request.turns.map((turn) => ({
          turn_index: turn.turn_index,
          idempotency_key: turn.idempotency_key,
          hmac: turn.hmac,
        })),
        entry,
      ];
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        body: streamOf([
          frame("content", { text: "About 68 million." }, 1),
          frame(
            "terminal",
            {
              state: "complete",
              ...entry,
              state_slots: SLOTS,
              compacted_summary: null,
              window,
            },
            2,
          ),
        ]),
      };
    });

    await act(() => result.current.chat.send("What is the population of France?"));
    await act(() => result.current.chat.send("And Germany?"));

    const first = requestBody(fetchMock, 0);
    expect(first.turns).toEqual([]);
    expect(first.compacted_summary).toBeNull();
    expect(result.current.turns[0]).toMatchObject({
      idempotencyKey: first.idempotency_key,
      turnIndex: 0,
      hmac: sig("0"),
      stateSlots: SLOTS,
    });
    expect(result.current.turns[1]).toMatchObject({
      turnIndex: 1,
      hmac: sig("1"),
    });
    const second = requestBody(fetchMock, 1);
    expect(second).not.toHaveProperty("history");
    expect(second.idempotency_key).not.toBe(first.idempotency_key);
    expect(second.turns).toEqual([
      {
        turn_index: 0,
        idempotency_key: first.idempotency_key,
        user_query: "What is the population of France?",
        model_response: "About 68 million.",
        state_slots: SLOTS,
        hmac: sig("0"),
      },
    ]);
    expect(second.compacted_summary).toBeNull();
  });

  it("clears every signature when the agent rejects the transcript", async () => {
    // Test: An unverifiable transcript clears stored signatures so the session
    //   recovers.
    // Situation: Two signed turns exist, and the agent answers the next
    //   request with HTTP 400 and reason `transcript_invalid`.
    // Expectation: The new turn ends with the rejection message, every
    //   earlier turn loses its signature and summary, and the next request
    //   sends no context.
    const { result, fetchMock } = renderChat(
      [],
      [signedTurn(0), signedTurn(1, { compactedSummary: "Earlier turns." })],
    );
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      body: null,
      json: async () => ({ detail: { reason: "transcript_invalid" } }),
    });

    await act(() => result.current.chat.send("And Germany?"));

    expect(requestBody(fetchMock, 0).turns).toHaveLength(2);
    const turns = result.current.turns;
    expect(turns[2].status).toBe("error");
    expect(turns[2].error).toBe(TRANSCRIPT_REJECTED_ERROR);
    expect(result.current.chat.error).toBe(TRANSCRIPT_REJECTED_ERROR);
    expect(turns.slice(0, 2).map((turn) => turn.hmac)).toEqual([
      undefined,
      undefined,
    ]);
    expect(turns[1].compactedSummary).toBeUndefined();
    expect(transcriptRequestFields(turns).turns).toEqual([]);
  });

  it("keeps signatures on a 400 that is not a transcript rejection", async () => {
    // Test: Only the agent's transcript rejection clears context.
    // Situation: A 400 response arrives whose body is not the agent's
    //   rejection, as from a proxy.
    // Expectation: The turn fails with the HTTP status, and earlier turns
    //   keep their signatures.
    const { result, fetchMock } = renderChat([], [signedTurn(0)]);
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      body: null,
      json: async () => {
        throw new SyntaxError("not json");
      },
    });

    await act(() => result.current.chat.send("And Germany?"));

    expect(result.current.turns[1].error).toBe("HTTP 400 Bad Request");
    expect(result.current.turns[0].hmac).toBe(sig("0"));
  });

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
    const body = requestBody(fetchMock, 0);
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
