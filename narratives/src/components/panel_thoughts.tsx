/**
 * @fileoverview Groups and renders agent thoughts by phase.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ThoughtEvent } from "../hooks/use_sse_chat";

interface ThoughtsPanelProps {
  thoughts: ThoughtEvent[];
}

/**
 * Streamed "thinking" text the model emits with thinkingConfig.includeThoughts=true.
 * Rendered inline, always expanded — no collapse/expand toggle, no header.
 */
export function ThoughtsPanel({ thoughts }: ThoughtsPanelProps) {
  if (thoughts.length === 0) return null;

  const grouped = groupByPhase(thoughts);

  return (
    <div className="self-start w-full max-w-4xl">
      <div className="mt-2 flex flex-col gap-3 text-body-medium text-on-surface-variant pl-6 border-l border-line">
          {grouped.map(([phase, items]) => (
            <div key={phase} className="flex flex-col gap-1">
              <div className="text-xs uppercase tracking-wide text-on-surface-variant">
                {phase}
              </div>
              {items.map((thought, index) => (
                <div key={index} className="leading-relaxed thought-markdown">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      // Compact, inline-feeling typography for thoughts:
                      // smaller margins, lighter headings, same paragraph
                      // spacing as surrounding body-medium text.
                      p: ({ children }) => (
                        <p className="mb-2 last:mb-0">{children}</p>
                      ),
                      h1: ({ children }) => (
                        <p className="font-semibold mt-2 mb-1 text-on-surface">
                          {children}
                        </p>
                      ),
                      h2: ({ children }) => (
                        <p className="font-semibold mt-2 mb-1 text-on-surface">
                          {children}
                        </p>
                      ),
                      h3: ({ children }) => (
                        <p className="font-semibold mt-2 mb-1 text-on-surface">
                          {children}
                        </p>
                      ),
                      h4: ({ children }) => (
                        <p className="font-semibold mt-2 mb-1 text-on-surface">
                          {children}
                        </p>
                      ),
                      strong: ({ children }) => (
                        <strong className="font-semibold text-on-surface">
                          {children}
                        </strong>
                      ),
                      em: ({ children }) => (
                        <em className="italic">{children}</em>
                      ),
                      ul: ({ children }) => (
                        <ul className="list-disc pl-5 mb-2 space-y-0.5">
                          {children}
                        </ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="list-decimal pl-5 mb-2 space-y-0.5">
                          {children}
                        </ol>
                      ),
                      code: ({ children }) => (
                        <code className="px-1 rounded bg-gray-100 text-[0.92em] font-mono">
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
                    {thought.text}
                  </ReactMarkdown>
                </div>
              ))}
            </div>
          ))}
      </div>
    </div>
  );
}

/** Groups thoughts by pipeline phase, in fixed mcp → kb → synthesis order. */
function groupByPhase(
  thoughts: ThoughtEvent[],
): Array<[ThoughtEvent["phase"], ThoughtEvent[]]> {
  const order: ThoughtEvent["phase"][] = ["mcp", "kb", "synthesis"];
  const map = new Map<ThoughtEvent["phase"], ThoughtEvent[]>();
  for (const thought of thoughts) {
    if (!map.has(thought.phase)) map.set(thought.phase, []);
    map.get(thought.phase)!.push(thought);
  }
  return order
    .filter((phase) => map.has(phase))
    .map(
      (phase) => [phase, map.get(phase)!] as [ThoughtEvent["phase"], ThoughtEvent[]],
    );
}
