/**
 * @fileoverview Renders a chip describing a single MCP tool call.
 */

import type { ToolCallEvent } from "../hooks/use_sse_chat";

/** Argument keys worth surfacing in the chip summary, per tool. */
const KEYS_BY_TOOL: Record<string, string[]> = {
  get_observations: ["variable_dcid", "entity_dcids", "date"],
  search_indicators: ["query", "places"],
};

/** For tools without a curated key list, show at most this many arguments. */
const MAX_NUM_KEYS = 3;
/** Truncate string argument values longer than this in the summary. */
const MAX_STRING_LENGTH = 30;
/** Show at most this many elements of an array argument value. */
const MAX_NUM_VALUES = 3;

interface ToolCallChipProps {
  toolCall: ToolCallEvent;
}

/**
 * Pretty-prints one MCP tool call as a small inline pill, e.g.
 *   search_indicators("average_annual_wage", places=["country/USA"])
 */
export function ToolCallChip({ toolCall }: ToolCallChipProps) {
  const args = toolCall.arguments ?? {};
  const summary = describeArguments(toolCall.name, args);
  const failed = toolCall.status === "error";
  return (
    <span
      className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-label-large ${
        failed ? "bg-error-surface text-error-strong" : "bg-surface-blue text-brand-primary"
      }`}
      title={JSON.stringify(args)}
    >
      <code className="font-mono text-xs">{toolCall.name}</code>
      <span className="text-xs text-on-surface-variant">{summary}</span>
    </span>
  );
}

/** Formats and truncates individual argument values for readable display. */
function formatArgValue(value: unknown): string {
  if (Array.isArray(value)) {
    const sliced = value.slice(0, MAX_NUM_VALUES);
    const hasMore = value.length > MAX_NUM_VALUES;
    return `[${sliced.join(",")}${hasMore ? ",…" : ""}]`;
  }
  if (typeof value === "string") {
    const isTooLong = value.length > MAX_STRING_LENGTH;
    return isTooLong ? `${value.slice(0, MAX_STRING_LENGTH)}…` : value;
  }
  return String(value);
}

/** Builds the `(key=value, …)` summary of a tool call's arguments. */
function describeArguments(
  toolCallName: string,
  args: Record<string, unknown>,
): string {
  const keysOfInterest =
    KEYS_BY_TOOL[toolCallName] ?? Object.keys(args).slice(0, MAX_NUM_KEYS);

  const parts: string[] = [];
  for (const key of keysOfInterest) {
    const value = args[key];
    if (value === undefined || value === null) continue;
    parts.push(`${key}=${formatArgValue(value)}`);
  }
  return parts.length ? `(${parts.join(", ")})` : "";
}
