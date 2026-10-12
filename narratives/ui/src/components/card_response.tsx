/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Renders streamed agent markdown with inline citations.
 */

import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useContext,
  useMemo,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  CitationChip,
  HideCitationsProvider,
  renderWithCitations,
} from "./chip_citation";
import {
  analyzeMarkdownTable,
  citationsIn,
  textOf,
  type MarkdownNode,
  type TableAnalysis,
} from "../utils/markdown_table";
import { rehypeStreamWords } from "../utils/rehype_stream_words";
import type { ProvenanceItem } from "../hooks/use_sse_chat";

interface ResponseCardProps {
  title: string;
  body: string;
  streaming?: boolean;
  // The answer's provenance list, so an inline [n] chip can name the source
  // it points at rather than showing a bare number. Position n is chip [n] --
  // the same order the synthesis prompt numbered and CitationsList renders.
  sources?: ProvenanceItem[];
  // When true, renders the markdown body only — no outer card, no title
  // bar. Used inside AnswerPanel's "Side panel" card where the user's
  // question is already shown in the toolbar.
  bare?: boolean;
  // When set, the body reveals word by word in reading order over this many
  // milliseconds. Left unset the body is simply there.
  streamMs?: number;
}

const LINK_COLOR = "var(--color-theme-primary)";

/** Renders the agent's answer text as markdown, with citation chips. */
export function ResponseCard({
  title,
  body,
  streaming,
  sources,
  bare = false,
  streamMs,
}: ResponseCardProps) {
  const markdown = (
    <div
      className={`${bare ? "" : "px-[56px] py-6 text-on-surface "}markdown-body${
        streamMs === undefined ? "" : " markdown-stream"
      }`}
    >
      <ReactMarkdownInner body={body} sources={sources} streamMs={streamMs} />
    </div>
  );

  if (bare) {
    return markdown;
  }

  return (
    <div className="self-start w-full border border-outline rounded-card overflow-hidden shadow-sm bg-surface-narrative">
      <div className="px-6 py-4 border-b border-outline-variant flex justify-between items-center bg-surface">
        <h3 className="text-label-large text-on-surface">{title}</h3>
        {streaming && (
          <span className="inline-flex items-center gap-1 text-xs text-on-surface-variant">
            <span className="w-2 h-2 rounded-full bg-theme-primary animate-pulse" />
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
  sources,
  streamMs,
}: {
  body: string;
  sources?: ProvenanceItem[];
  streamMs?: number;
}) {
  // Memoized because react-markdown uses each of these functions as a
  // component type. Built inline they are new functions on every render, so
  // React takes every element for a different component and replaces the whole
  // rendered answer -- which restarts the reveal each time the turn updates.
  const components = useMemo(
    (): Components => ({
            // The word wrappers rehypeStreamWords adds. Citation markers and
            // long numbers sit inside them, so they get the same treatment
            // as any other run of text.
            span: ({ children, className, style }) => (
              <span className={className} style={style}>
                {renderWithCitations(children, sources)}
              </span>
            ),
            p: ({ children }) => (
              <p className="text-body-large mb-3 last:mb-0">
                {renderWithCitations(children, sources)}
              </p>
            ),
            h1: ({ children }) => (
              <h1 className="text-2xl font-medium mt-4 mb-2">
                {renderWithCitations(children, sources)}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-xl font-medium mt-4 mb-2">
                {renderWithCitations(children, sources)}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-lg font-medium mt-3 mb-2">
                {renderWithCitations(children, sources)}
              </h3>
            ),
            h4: ({ children }) => (
              <h4 className="text-base font-medium mt-3 mb-2">
                {renderWithCitations(children, sources)}
              </h4>
            ),
            em: ({ children }) => (
              <em className="italic">{renderWithCitations(children, sources)}</em>
            ),
            ul: ({ children }) => (
              <ul className="list-disc pl-6 mb-3 space-y-1">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="list-decimal pl-6 mb-3 space-y-1">{children}</ol>
            ),
            // `style` on li, blockquote, table and hr carries their stream
            // delay, so a bullet or a rule waits for the text it belongs to.
            li: ({ children, style }) => (
              <li className="leading-relaxed" style={style}>
                {renderWithCitations(children, sources)}
              </li>
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
            blockquote: ({ children, style }) => (
              <blockquote
                className="border-l-4 border-outline pl-4 italic text-on-surface-variant mb-3"
                style={style}
              >
                {renderWithCitations(children, sources)}
              </blockquote>
            ),
            table: (props) => <MarkdownTable {...props} />,
            thead: ({ children }) => (
              <thead className="bg-surface-soft">{children}</thead>
            ),
            tr: (props) => <MarkdownRow {...props} />,
            th: (props) => <HeaderCell {...props} sources={sources} />,
            td: (props) => <DataCell {...props} sources={sources} />,
            strong: ({ children }) => (
              <strong className="font-semibold">
                {renderWithCitations(children, sources)}
              </strong>
            ),
            hr: ({ style }) => (
              <hr className="my-4 border-outline" style={style} />
            ),
    }),
    [sources],
  );

  return (
    <>
      <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={
            streamMs === undefined ? [] : [[rehypeStreamWords, streamMs]]
          }
          components={components}
        >
          {body}
        </ReactMarkdown>
    </>
  );
}

/** What a cell needs from the table around it; empty outside a table. */
const EMPTY_ANALYSIS: TableAnalysis = {
  numericColumns: new Set<number>(),
  hoistedCitations: new Map<number, number[]>(),
};

const TableAnalysisContext = createContext<TableAnalysis>(EMPTY_ANALYSIS);

/** Props a markdown cell or row gets, plus what this file threads through. */
interface MarkdownCellProps {
  children?: ReactNode;
  /** The HTML AST node react-markdown built this element from. */
  node?: unknown;
  /** Position in the row, injected by {@link MarkdownRow}. */
  colIndex?: number;
  /** Alignment the markdown asked for explicitly (`:---:`), if any. */
  style?: CSSProperties;
  sources?: ProvenanceItem[];
}

/** A markdown table, with the whole-column facts read off the AST once. */
function MarkdownTable({ children, node, style }: MarkdownCellProps) {
  const analysis = useMemo(
    () => analyzeMarkdownTable(node as MarkdownNode | undefined),
    [node],
  );
  return (
    <TableAnalysisContext.Provider value={analysis}>
      <div className="overflow-x-auto mb-3">
        <table className="min-w-full text-sm border-collapse" style={style}>
          {children}
        </table>
      </div>
    </TableAnalysisContext.Provider>
  );
}

/**
 * A table row that tells each cell which column it is in. react-markdown hands
 * a cell its own node and nothing about its siblings, so there is no other way
 * for it to find out.
 */
function MarkdownRow({ children }: MarkdownCellProps) {
  let column = 0;
  return (
    <tr>
      {Children.map(children, (child) =>
        isValidElement(child)
          ? cloneElement(child as ReactElement<MarkdownCellProps>, {
              colIndex: column++,
            })
          : child,
      )}
    </tr>
  );
}

/** Alignment: what the markdown asked for, else right when numeric. */
function cellAlignment(
  style: CSSProperties | undefined,
  numeric: boolean,
  fallback: CSSProperties["textAlign"],
): CSSProperties["textAlign"] {
  if (style?.textAlign) return style.textAlign;
  return numeric ? "right" : fallback;
}

/**
 * A header cell, carrying its column's citation when every body cell in the
 * column cited the same source. Appended only when the header does not
 * already state it.
 */
function HeaderCell({
  children,
  node,
  colIndex,
  style,
  sources,
}: MarkdownCellProps) {
  const { numericColumns, hoistedCitations } = useContext(TableAnalysisContext);
  const numeric = colIndex !== undefined && numericColumns.has(colIndex);
  const hoisted =
    (colIndex !== undefined ? hoistedCitations.get(colIndex) : undefined) ?? [];
  const alreadyStated = new Set(citationsIn(textOf(node as MarkdownNode)));
  const toAppend = hoisted.filter((n) => !alreadyStated.has(n));

  return (
    <th
      className="border border-outline px-3 py-2 font-medium"
      style={{ ...style, textAlign: cellAlignment(style, numeric, "left") }}
    >
      {renderWithCitations(children, sources)}
      {toAppend.map((n) => (
        <span key={n}> <CitationChip n={n} sources={sources} /></span>
      ))}
    </th>
  );
}

/**
 * A body cell, set right when its column holds values. `tabular-nums` too:
 * proportional digits leave the decimal points ragged even when flush right.
 */
function DataCell({ children, colIndex, style, sources }: MarkdownCellProps) {
  const { numericColumns, hoistedCitations } = useContext(TableAnalysisContext);
  const numeric = colIndex !== undefined && numericColumns.has(colIndex);
  const hoisted = colIndex !== undefined && hoistedCitations.has(colIndex);

  return (
    <td
      className={`border border-outline px-3 py-2${
        numeric ? " tabular-nums" : ""
      }`}
      style={{ ...style, textAlign: cellAlignment(style, numeric, undefined) }}
    >
      <HideCitationsProvider value={hoisted}>
        {renderWithCitations(children, sources)}
      </HideCitationsProvider>
    </td>
  );
}
