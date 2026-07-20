/**
 * @fileoverview Renders streamed agent markdown with inline citations.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { renderWithCitations } from "./chip_citation";

interface ResponseCardProps {
  title: string;
  body: string;
  streaming?: boolean;
  // When true, renders the markdown body only — no outer card, no title
  // bar. Used inside AnswerPanel's "Side panel" card where the user's
  // question is already shown in the toolbar.
  bare?: boolean;
}

/**
 * Renders the agent's streamed synthesis as actual markdown. Bold,
 * italics, lists, links, tables, code spans, and backslash-escaped
 * underscores (e.g. `average\_annual\_wage`) all parse correctly.
 * GFM enables tables + autolinks + strikethrough.
 */

const LINK_COLOR = "var(--color-brand-primary)"; // Figma "AI Dark Blue" (brand primary)

/** Renders the agent's answer text as markdown, with citation chips and streaming cursor. */
export function ResponseCard({
  title,
  body,
  streaming,
  bare = false,
}: ResponseCardProps) {
  const markdown = (
    <div className={bare ? "markdown-body" : "px-[56px] py-6 text-on-surface markdown-body"}>
      <ReactMarkdownInner body={body} streaming={streaming} />
    </div>
  );

  if (bare) {
    return markdown;
  }

  return (
    <div className="self-start w-full border border-outline rounded-[24px] overflow-hidden shadow-sm bg-surface-soft">
      <div className="px-6 py-4 border-b border-outline-variant flex justify-between items-center bg-surface">
        <h3 className="text-label-large text-on-surface">{title}</h3>
        {streaming && (
          <span className="inline-flex items-center gap-1 text-xs text-on-surface-variant">
            <span className="w-2 h-2 rounded-full bg-brand-primary animate-pulse" />
            streaming
          </span>
        )}
      </div>
      {markdown}
    </div>
  );
}

/**
 * Markdown rendering body extracted so both `bare` and chrome'd modes
 * share the same component overrides (citation chips, table styling).
 */
function ReactMarkdownInner({
  body,
  streaming,
}: {
  body: string;
  streaming?: boolean;
}) {
  return (
    <>
      <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => (
              <p className="text-body-large mb-3 last:mb-0">
                {renderWithCitations(children)}
              </p>
            ),
            h1: ({ children }) => (
              <h1 className="text-2xl font-medium mt-4 mb-2">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-xl font-medium mt-4 mb-2">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-lg font-medium mt-3 mb-2">{children}</h3>
            ),
            h4: ({ children }) => (
              <h4 className="text-base font-medium mt-3 mb-2">{children}</h4>
            ),
            em: ({ children }) => <em className="italic">{children}</em>,
            ul: ({ children }) => (
              <ul className="list-disc pl-6 mb-3 space-y-1">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="list-decimal pl-6 mb-3 space-y-1">{children}</ol>
            ),
            li: ({ children }) => (
              <li className="leading-relaxed">{renderWithCitations(children)}</li>
            ),
            a: ({ children, href }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
                style={{ color: LINK_COLOR }}
              >
                {children}
              </a>
            ),
            code: ({ children, ...props }) => {
              const inline = !(
                "className" in (props as Record<string, unknown>) &&
                /language-/.test(
                  ((props as Record<string, unknown>).className as string) ||
                    "",
                )
              );
              return inline ? (
                <code className="px-1 py-0.5 rounded bg-surface-muted text-[0.92em] font-mono">
                  {children}
                </code>
              ) : (
                <code className="font-mono">{children}</code>
              );
            },
            pre: ({ children }) => (
              <pre className="bg-surface-soft border border-outline rounded-md p-3 overflow-auto text-sm mb-3">
                {children}
              </pre>
            ),
            blockquote: ({ children }) => (
              <blockquote className="border-l-4 border-outline pl-4 italic text-on-surface-variant mb-3">
                {children}
              </blockquote>
            ),
            table: ({ children }) => (
              <div className="overflow-x-auto mb-3">
                <table className="min-w-full text-sm border-collapse">
                  {children}
                </table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="bg-surface-soft">{children}</thead>
            ),
            th: ({ children }) => (
              <th className="border border-outline px-3 py-2 text-left font-medium">
                {renderWithCitations(children)}
              </th>
            ),
            td: ({ children }) => (
              <td className="border border-outline px-3 py-2">
                {renderWithCitations(children)}
              </td>
            ),
            strong: ({ children }) => (
              <strong className="font-semibold">
                {renderWithCitations(children)}
              </strong>
            ),
            hr: () => <hr className="my-4 border-outline" />,
          }}
        >
          {body}
        </ReactMarkdown>
        {streaming && (
          <span className="inline-block animate-pulse">▍</span>
        )}
    </>
  );
}
