/**
 * @fileoverview Tests for restoring saved chat turns on page reload.
 */

import { describe, expect, it } from "vitest";
import { cleanTurns } from "./chat_session_context";
import { INTERRUPTED_TURN_ERROR, type ChatTurn } from "./use_sse_chat";

const turn = (overrides: Partial<ChatTurn>): ChatTurn => ({
  userMessage: "What is the population of France?",
  status: "done",
  toolCalls: [],
  thoughts: [],
  text: "",
  provenance: [],
  ...overrides,
});

describe("cleanTurns", () => {
  it("keeps settled turns unchanged", () => {
    // Test: Restoring finished turns.
    // Situation: Storage holds a done turn and an error turn.
    // Expectation: Both are restored exactly as saved.
    const done = turn({ status: "done", text: "About 68 million." });
    const failed = turn({ status: "error", error: "The data request failed." });

    expect(cleanTurns([done, failed])).toEqual([done, failed]);
  });

  it.each(["idle", "mcp", "synthesis"] as const)(
    "turns a %s turn into an interrupted error turn instead of dropping it",
    (status) => {
      // Test: Restoring a turn that was mid-stream when the page closed.
      // Situation: Storage holds a turn in a streaming status with partial
      //   text.
      // Expectation: The turn is kept, with its question and partial text,
      //   as an error turn carrying the interrupted-connection message.
      const [restored] = cleanTurns([turn({ status, text: "About 68" })]);

      expect(restored).toEqual(
        turn({ status: "error", text: "About 68", error: INTERRUPTED_TURN_ERROR }),
      );
    },
  );

  it("drops entries that are not turns and tolerates a non-array", () => {
    // Test: Corrupted storage.
    // Situation: The saved turns hold null and a string beside a real turn,
    //   or are not an array at all.
    // Expectation: Only the valid turn is kept, and a non-array input returns
    //   an empty array.
    const done = turn({});
    const corrupted = [null, "turn", done] as unknown as ChatTurn[];

    expect(cleanTurns(corrupted)).toEqual([done]);
    expect(cleanTurns("turns" as unknown as ChatTurn[])).toEqual([]);
  });
});
