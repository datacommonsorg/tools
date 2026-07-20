/**
 * @fileoverview Renders the agent's collapsible reasoning/thoughts block for a turn.
 */

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDownIcon } from "./icons";
import type { ThoughtEvent, TurnStatus } from "../hooks/use_sse_chat";

/**
 * Figma "Sparkle + Extension chip" (node 3427:16720) + "Content" (3427:16723).
 * Header row: Gemini sparkle icon (left) + "Reasoning ▾" chip (right of it).
 * Body: model reasoning text, expanded by default.
 *
 * Tokens:
 *   Header gap 12, items centered
 *   Label "Reasoning" — Google Sans Text Medium 14/20 (Type scale - Desktop/Label L)
 *   Chevron — Material keyboard_arrow_down
 *   Default expanded; chevron rotates 180° when collapsed
 */

const COLOR_TEXT = "var(--color-on-surface)";
const COLOR_SPARKLE = "#1A8C7A";
const FONT_LABEL =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface ReasoningBlockProps {
  thoughts: ThoughtEvent[];
  defaultOpen?: boolean;
  // True while the chat turn is still streaming. Lets the placeholder
  // body adapt ("Reasoning…" vs. final fallback) when the agent emits
  // no `thought` events (e.g. simple queries with low thinking level).
  streaming?: boolean;
  // True once the turn is finished (status === "done"). Together with
  // an empty thoughts array, controls whether we show a "completed"
  // fallback message.
  done?: boolean;
  // Drives the header label + leading icon. During streaming we show a
  // phase-specific label ("Querying data tools…", "Synthesizing answer…")
  // with the rotating loader; once done we switch to "Reasoning" with
  // the sparkle icon.
  status?: TurnStatus;
}

const PLACEHOLDER_STREAMING =
  "Searching Data Commons for relevant indicators and observations…";
const PLACEHOLDER_DONE =
  "Analyzed the query and retrieved relevant data from Data Commons.";

/**
 * Header label is derived from the turn status. Server emits status
 * transitions (`mcp_start` → `mcp_complete` → `synthesis_start` → `done`);
 * these strings are the UI-side copy for each phase.
 */
function phaseLabel(streaming: boolean, status?: TurnStatus): string {
  if (!streaming) return "Reasoning";
  switch (status) {
    case "mcp":
      return "Querying data tools…";
    case "kb":
      return "Searching knowledge base…";
    case "synthesis":
      return "Synthesizing answer…";
    default:
      return "Thinking…";
  }
}

/** Collapsible "Reasoning" block: sparkle header plus the streamed thinking text. */
export function ReasoningBlock({
  thoughts,
  defaultOpen = true,
  streaming = false,
  done = false,
  status,
}: ReasoningBlockProps) {
  const [open, setOpen] = useState(defaultOpen);
  const label = phaseLabel(streaming, status);

  // Flatten to a single markdown string (newline-separated). Phase grouping
  // existed in the old ThoughtsPanel; the new Figma design renders the
  // reasoning as one continuous block. When the agent emits no thoughts,
  // we render a short status placeholder so the section stays present
  // above the response card per Figma 3427-16715.
  const joined =
    thoughts.length > 0
      ? thoughts.map((thought) => thought.text).join("\n\n")
      : streaming
        ? PLACEHOLDER_STREAMING
        : done
          ? PLACEHOLDER_DONE
          : "";

  // If we have nothing at all (e.g. error before stream started),
  // skip rendering entirely.
  if (!joined) return null;

  return (
    <div className="self-start shrink-0 w-full max-w-4xl">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center gap-3 bg-transparent border-0 p-0 cursor-pointer"
        aria-expanded={open}
      >
        {streaming ? <LoaderSpinner /> : <SparkleIcon />}
        <span
          className="inline-flex items-center gap-1"
          style={{
            fontFamily: FONT_LABEL,
            fontSize: 14,
            lineHeight: "20px",
            fontWeight: 500,
            color: COLOR_TEXT,
          }}
        >
          {label}
          <ChevronDownIcon
            className={`text-on-surface-variant transition-transform duration-150 ${
              open ? "rotate-0" : "-rotate-90"
            }`}
          />
        </span>
      </button>
      {open && (
        <div
          className="mt-2 reasoning-markdown"
          style={{
            fontFamily: FONT_LABEL,
            fontSize: 16,
            lineHeight: "28px",
            color: COLOR_TEXT,
          }}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => (
                <p className="m-0 mb-2 last:mb-0">{children}</p>
              ),
              strong: ({ children }) => (
                <strong style={{ fontWeight: 600 }}>{children}</strong>
              ),
              em: ({ children }) => (
                <em style={{ fontStyle: "italic" }}>{children}</em>
              ),
              ul: ({ children }) => (
                <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal pl-5 mb-2 space-y-0.5">
                  {children}
                </ol>
              ),
              code: ({ children }) => (
                <code
                  className="px-1 rounded font-mono"
                  style={{ backgroundColor: "#F2F2F2", fontSize: "0.92em" }}
                >
                  {children}
                </code>
              ),
              a: ({ children, href }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline"
                  style={{ color: "var(--color-brand-primary)" }}
                >
                  {children}
                </a>
              ),
            }}
          >
            {joined}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

/**
 * Rotating loader shown while the turn is still streaming.
 * Uses the public/loader.png asset already shipped by the app.
 */
function LoaderSpinner() {
  return (
    <img
      src="/loader.png"
      alt=""
      aria-hidden="true"
      width={20}
      height={20}
      style={{
        flexShrink: 0,
        animation: "reasoning-spin 1s linear infinite",
      }}
    />
  );
}

/**
 * Gemini-style 4-point sparkle, filled with the brand primary color.
 * Matches the icon shown in the Figma screenshot — a four-pointed star
 * with concave sides.
 */
function SparkleIcon() {
  return (
    <svg
      width={20}
      height={20}
      viewBox="0 0 24 24"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <path
        d="M12 2 L13.6 8.5 C13.9 9.7 14.5 10.5 15.5 10.85 L22 12 L15.5 13.15 C14.5 13.5 13.9 14.3 13.6 15.5 L12 22 L10.4 15.5 C10.1 14.3 9.5 13.5 8.5 13.15 L2 12 L8.5 10.85 C9.5 10.5 10.1 9.7 10.4 8.5 Z"
        fill={COLOR_SPARKLE}
      />
    </svg>
  );
}

