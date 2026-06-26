/**
 * @fileoverview Tool-call chip — pretty-prints one MCP tool call as a small
 * inline pill, e.g. search_indicators("average_annual_wage", places=["country/USA"]).
 */

import type { ToolCallEvent } from "../hooks/use_sse_chat";

interface ChipToolCallProps {
  toolCall: ToolCallEvent;
}

// Maximum number of argument keys to display when a tool isn't in KEYS_BY_TOOL.
const MAX_NUM_KEYS = 3;
// Maximum number of array elements to render inside a single argument value.
const MAX_NUM_VALUES = 3;
// Maximum length of a string argument value before it's truncated with an ellipsis.
const MAX_STRING_LENGTH = 30;

// The most useful argument keys to surface per known tool, in display order.
const KEYS_BY_TOOL: Record<string, string[]> = {
  get_observations: ["variable_dcid", "entity_dcids", "date"],
  search_indicators: ["query", "places"],
};

/**
 * Renders a single MCP tool call as a compact pill, summarizing its most
 * relevant arguments and reflecting an error state when the call failed.
 */
export function ChipToolCall({ toolCall }: ChipToolCallProps) {
  const args = toolCall.arguments ?? {};
  const summary = describeArguments(toolCall.name, args);
  const failed = toolCall.status === "error";
  return (
    <span
      className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-label-large ${
        failed ? "bg-red-50 text-red-700" : "bg-surface-blue text-brand-primary-dark"
      }`}
      title={JSON.stringify(args)}
    >
      <code className="font-mono text-xs">{toolCall.name}</code>
      <span className="text-xs text-on-surface-variant">{summary}</span>
    </span>
  );
}

/**
 * Formats and truncates an individual argument value for readable display.
 */
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

/**
 * Builds the parenthesized argument summary for a tool call, picking the
 * keys of interest for known tools and falling back to the first few keys
 * otherwise.
 */
function describeArguments(
  toolCallName: string,
  args: Record<string, unknown>,
): string {
  const keysOfInterest =
    KEYS_BY_TOOL[toolCallName] ?? Object.keys(args).slice(0, MAX_NUM_KEYS);

  const parts: string[] = [];
  for (const key of keysOfInterest) {
    const value = args[key];
    if (value === undefined || value === null) {
      continue;
    }
    parts.push(`${key}=${formatArgValue(value)}`);
  }
  return parts.length ? `(${parts.join(", ")})` : "";
}
