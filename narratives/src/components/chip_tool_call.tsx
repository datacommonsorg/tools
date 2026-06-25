import type { ToolCallEvent } from "../hooks/use_sse_chat";

interface ChipToolCallProps {
  toolCall: ToolCallEvent;
}

// Pretty-prints one MCP tool call as a small inline pill, e.g.
//   search_indicators("average_annual_wage", places=["country/USA"])
export default function ChipToolCall({ toolCall }: ChipToolCallProps) {
  const args = toolCall.arguments ?? {};
  const summary = describeArguments(toolCall.name, args);
  const failed = toolCall.status === "error";
  return (
    <span
      className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-label-large ${
        failed ? "bg-red-50 text-red-700" : "bg-surface-blue text-teal"
      }`}
      title={JSON.stringify(args)}
    >
      <code className="font-mono text-xs">{toolCall.name}</code>
      <span className="text-xs text-on-surface-variant">{summary}</span>
    </span>
  );
}

function describeArguments(name: string, args: Record<string, unknown>): string {
  const keysOfInterest =
    name === "get_observations"
      ? ["variable_dcid", "entity_dcids", "date"]
      : name === "search_indicators"
        ? ["query", "places"]
        : Object.keys(args).slice(0, 3);

  const parts: string[] = [];
  for (const k of keysOfInterest) {
    if (args[k] === undefined || args[k] === null) continue;
    const v = args[k];
    if (Array.isArray(v)) {
      parts.push(`${k}=[${v.slice(0, 3).join(",")}${v.length > 3 ? ",…" : ""}]`);
    } else if (typeof v === "string") {
      parts.push(`${k}=${v.length > 30 ? v.slice(0, 30) + "…" : v}`);
    } else {
      parts.push(`${k}=${String(v)}`);
    }
  }
  return parts.length ? `(${parts.join(", ")})` : "";
}
