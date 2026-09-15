/**
 * @fileoverview Renders the agent's collapsible reasoning/thoughts block for a turn.
 */

import { useState, type CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDownIcon } from "./icons";
import type { ThoughtEvent, TurnStatus } from "../hooks/use_sse_chat";

/**
 * Figma "Sparkle + Extension chip" (node 3427:16720) + "Content" (3427:16723).
 * Header row: Gemini sparkle icon (left) + "Reasoning ▾" chip (right of it).
 * Body: model reasoning text, collapsed by default.
 *
 * Tokens:
 *   Header gap 12, items centered
 *   Label "Reasoning" — Google Sans Text Medium 14/20 (Type scale - Desktop/Label L)
 *   Chevron — Material keyboard_arrow_down
 *   Default collapsed; chevron rotates 180° when expanded
 */

const COLOR_TEXT = "var(--color-on-surface)";
/** Reasoning body reads as a muted aside — one step softer than the response. */
const COLOR_REASONING = "var(--color-on-surface-variant)";
const FONT_LABEL =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

// The reasoning aside's left bar. The bar lives on the content blocks — both
// headings and body (paragraphs, lists) — so each heading + its following body
// share one continuous bar. Consecutive blocks have no vertical margin so their
// borders touch; a heading's top margin opens a gap with no border, which is
// what breaks the bar before the *next* heading.
const BAR_WIDTH = 2;
const BAR_PAD = 16;
const BAR_INSET = BAR_WIDTH + BAR_PAD; // left offset of body text (border + pad)
const BAR_COLOR = "var(--color-border, #E3E3E3)";
// The reasoning icon (sparkle/loader) is ICON_SIZE wide and starts at the
// aside's left edge, so its horizontal centre is at ICON_SIZE / 2. Shift the
// content right so the bar is centred under that icon centre.
const ICON_SIZE = 20;
const BAR_CENTER_LEFT = ICON_SIZE / 2 - BAR_WIDTH / 2;

/**
 * Body blocks: the barred, italic detail text. margin:0 + internal padding so
 * adjacent blocks' bars join seamlessly.
 */
const BODY_BLOCK_STYLE: CSSProperties = {
  margin: 0,
  borderLeft: `${BAR_WIDTH}px solid ${BAR_COLOR}`,
  paddingLeft: BAR_PAD,
  paddingTop: 2,
  paddingBottom: 2,
};

/**
 * Headings: bold, upright (not italic like the body), and barred like the body
 * so the section reads as one unit. marginTop opens the gap that breaks the bar
 * before this heading; marginBottom stays 0 so the heading joins its own body.
 */
const HEADING_STYLE: CSSProperties = {
  ...BODY_BLOCK_STYLE,
  marginTop: 14,
  paddingTop: 4,
  fontStyle: "normal",
  fontWeight: 600,
  fontSize: 16,
  lineHeight: "24px",
};

/** Renders a reasoning section heading — bold, upright, barred (HEADING_STYLE). */
const ReasoningHeading = ({ children }: { children?: React.ReactNode }) => (
  <h3 style={HEADING_STYLE}>{children}</h3>
);

/** Minimal shape of the hast node react-markdown hands each renderer. */
interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  children?: HastNode[];
}

/**
 * Reports whether a paragraph node is really a standalone bold line the model
 * wrote as a heading — e.g. `**Plan**` arrives as `<p><strong>…</strong></p>`,
 * not a real heading. We treat those as headings so the bar breaks at them
 * (models rarely emit `##` here).
 */
function isBoldOnlyParagraph(node?: HastNode): boolean {
  const kids = (node?.children ?? []).filter(
    (child) => !(child.type === "text" && !(child.value ?? "").trim()),
  );
  return (
    kids.length === 1 &&
    kids[0].type === "element" &&
    kids[0].tagName === "strong"
  );
}

interface ReasoningBlockProps {
  thoughts: ThoughtEvent[];
  // Whether the body starts expanded. Collapsed by default: the header alone
  // carries the phase label and spinner, which is the affordance that matters
  // while streaming — the thinking text is opt-in.
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
  if (!streaming) return "Reasoning details";
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
  defaultOpen = false,
  streaming = false,
  done = false,
  status,
}: ReasoningBlockProps) {
  const [open, setOpen] = useState(defaultOpen);
  const label = phaseLabel(streaming, status);

  // Flatten to a single markdown string (newline-separated): the reasoning
  // renders as one continuous block, not grouped per phase. When the agent
  // emits no thoughts, we render a short status placeholder so the section
  // stays present above the response card per Figma 3427-16715.
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
              open ? "rotate-180" : "rotate-0"
            }`}
          />
        </span>
      </button>
      {open && (
        <div
          className="mt-2 reasoning-markdown"
          style={{
            marginLeft: BAR_CENTER_LEFT,
            fontFamily: FONT_LABEL,
            fontSize: 16,
            lineHeight: "28px",
            // Softer than the response body + italic + a left bar with
            // indentation, so the reasoning reads as an aside distinct from
            // the actual answer.
            color: COLOR_REASONING,
            fontStyle: "italic",
          }}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // Headings break the left bar (see HEADING_STYLE).
              h1: ReasoningHeading,
              h2: ReasoningHeading,
              h3: ReasoningHeading,
              h4: ReasoningHeading,
              h5: ReasoningHeading,
              h6: ReasoningHeading,
              // A lone-bold paragraph is really a section heading (breaks the
              // bar); everything else is a barred body paragraph.
              p: ({ node, children }) =>
                isBoldOnlyParagraph(node as unknown as HastNode) ? (
                  <h3 style={HEADING_STYLE}>{children}</h3>
                ) : (
                  <p style={BODY_BLOCK_STYLE}>{children}</p>
                ),
              strong: ({ children }) => (
                <strong style={{ fontWeight: 600 }}>{children}</strong>
              ),
              em: ({ children }) => (
                <em style={{ fontStyle: "italic" }}>{children}</em>
              ),
              ul: ({ children }) => (
                <ul
                  className="list-disc space-y-0.5"
                  style={{ ...BODY_BLOCK_STYLE, paddingLeft: BAR_INSET + 20 }}
                >
                  {children}
                </ul>
              ),
              ol: ({ children }) => (
                <ol
                  className="list-decimal space-y-0.5"
                  style={{ ...BODY_BLOCK_STYLE, paddingLeft: BAR_INSET + 20 }}
                >
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
 * Rotating agent mark shown while the turn is still streaming.
 *
 * The asset carries its own conic-gradient arc, so only the rotation is added
 * here. It is referenced rather than inlined because the gradient is a Figma
 * angular export (a `foreignObject` holding a CSS conic-gradient) and inlining
 * that much markup buys nothing.
 */
function LoaderSpinner() {
  return (
    <img
      src="/agent-thinking.svg"
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
 * Settled agent mark shown once the turn has finished streaming — the same
 * four-point star as {@link LoaderSpinner} without the surrounding arc.
 */
function SparkleIcon() {
  return (
    <img
      src="/agent-done-thinking.svg"
      alt=""
      aria-hidden="true"
      width={20}
      height={20}
      style={{ flexShrink: 0 }}
    />
  );
}

