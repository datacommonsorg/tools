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
  type CSSProperties,
  cloneElement,
  createContext,
  isValidElement,
  type ReactElement,
  type ReactNode,
  useContext,
  useMemo,
} from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  CitationChip,
  HideCitationsProvider,
  renderWithCitations,
} from '@/src/components/chip_citation';
import type { ProvenanceItem } from '@/src/hooks/use_sse_chat';
import {
  analyzeMarkdownTable,
  citationsIn,
  type MarkdownNode,
  type TableAnalysis,
  textOf,
} from '@/src/utils/markdown_table';
import { rehypeStreamWords } from '@/src/utils/rehype_stream_words';

interface ResponseCardProps {
  title: string;
  body: string;
  // The answer's provenance list, so an inline [n] chip can name the source
  // it points at rather than showing a bare number. Position n is chip [n] --
  // the same order the synthesis prompt numbered and CitationsList renders.
  sources?: ProvenanceItem[];
  // When true, renders the markdown body only — no outer card, no title
  // bar. Used inside AnswerPanel's "Side panel" card where the user's
  // question is already shown in the toolbar.
  bare?: boolean;
  // When set, the content animates in over this many milliseconds. When
  // unset, it appears immediately.
  streamMs?: number;
  // Delay before the first word animates, in milliseconds, so a body that
  // follows another in one reveal starts where the previous one ends.
  streamStartMs?: number;
  // Whether the animation is still running. Once it ends the animation class
  // is dropped, so a copy of the DOM (the PDF export) does not replay it.
  revealing?: boolean;
}

/**
 * Markdown heading styles, by markdown level. The rendered element sits one
 * level down (`#` is an h2), since the answer panel's intro block owns the h1.
 * A bold-only paragraph is styled and ranked as a `###`.
 */
const HEADING_1_CLASS = 'text-2xl font-medium mt-4 mb-2';
const HEADING_2_CLASS = 'text-2xl font-medium mt-4 mb-2';
const HEADING_3_CLASS = 'text-xl font-medium mt-3 mb-2';
const HEADING_4_CLASS = 'text-base font-medium mt-3 mb-2';

/** Renders the agent's answer text as markdown, with citation chips. */
export function ResponseCard({
  title,
  body,
  sources,
  bare = false,
  streamMs,
  streamStartMs,
  revealing = streamMs !== undefined,
}: ResponseCardProps) {
  const markdown = (
    <div
      className={`${bare ? '' : 'text-on-surface '}markdown-body wrap-break-word${
        revealing ? ' markdown-stream' : ''
      }`}
    >
      <ReactMarkdownInner
        body={body}
        sources={sources}
        streamMs={streamMs}
        streamStartMs={streamStartMs}
      />
    </div>
  );

  if (bare) {
    return markdown;
  }

  return (
    <div className="self-start w-full border border-outline rounded-card overflow-hidden shadow-sm bg-surface-narrative">
      <div className="px-6 py-4 border-b border-outline-variant flex justify-between items-center bg-surface">
        <h3 className="text-label-large text-on-surface">{title}</h3>
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
  streamStartMs,
}: {
  body: string;
  sources?: ProvenanceItem[];
  streamMs?: number;
  streamStartMs?: number;
}) {
  // Memoized so streaming updates don't remount the answer and restart its
  // reveal.
  const components = useMemo(
    (): Components => ({
      // Word spans added by rehypeStreamWords. Citations and numbers
      // inside them render as in any other text.
      span: ({ children, className, style }) => (
        <StreamSpan className={className} style={style} sources={sources}>
          {children}
        </StreamSpan>
      ),
      p: ({ children, node }) => (
        <MarkdownParagraph node={node} sources={sources}>
          {children}
        </MarkdownParagraph>
      ),
      h1: ({ children }) => (
        <h2 className={HEADING_1_CLASS}>
          {renderWithCitations(children, sources)}
        </h2>
      ),
      h2: ({ children }) => (
        <h3 className={HEADING_2_CLASS}>
          {renderWithCitations(children, sources)}
        </h3>
      ),
      h3: ({ children }) => (
        <h4 className={HEADING_3_CLASS}>
          {renderWithCitations(children, sources)}
        </h4>
      ),
      h4: ({ children }) => (
        <h5 className={HEADING_4_CLASS}>
          {renderWithCitations(children, sources)}
        </h5>
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
          <NestedBlockContext.Provider value={true}>
            {renderWithCitations(children, sources)}
          </NestedBlockContext.Provider>
        </li>
      ),
      a: ({ children, href }) => (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-theme-primary hover:underline"
        >
          <PlainTextContext.Provider value={true}>
            {children}
          </PlainTextContext.Provider>
        </a>
      ),
      code: ({ children, ...props }) => {
        const inline = !(
          'className' in (props as Record<string, unknown>) &&
          /language-/.test(
            ((props as Record<string, unknown>).className as string) || '',
          )
        );
        const plain = (
          <PlainTextContext.Provider value={true}>
            {children}
          </PlainTextContext.Provider>
        );
        return inline ? (
          <code className="px-1 py-0.5 rounded bg-surface-muted text-[0.92em] font-mono">
            {plain}
          </code>
        ) : (
          <code className="font-mono">{plain}</code>
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
          <NestedBlockContext.Provider value={true}>
            {renderWithCitations(children, sources)}
          </NestedBlockContext.Provider>
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
      hr: ({ style }) => <hr className="my-4 border-outline" style={style} />,
    }),
    [sources],
  );

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={
        streamMs === undefined
          ? []
          : [[rehypeStreamWords, streamMs, streamStartMs]]
      }
      components={components}
    >
      {body}
    </ReactMarkdown>
  );
}

/**
 * True inside a list item or blockquote. A loose list wraps each item's text
 * in a paragraph, so a bold item there is emphasis, not a subheading.
 */
const NestedBlockContext = createContext(false);

/** Whether a paragraph's only content, whitespace aside, is one `strong`. */
function isBoldOnly(node: MarkdownNode | undefined): boolean {
  const content = (node?.children ?? []).filter(
    (child) => !(child.type === 'text' && !child.value?.trim()),
  );
  return content.length === 1 && content[0].tagName === 'strong';
}

/**
 * A paragraph, or a subheading when it is a top-level paragraph of nothing but
 * bold text: the model's way of writing one.
 */
function MarkdownParagraph({
  children,
  node,
  sources,
}: {
  children?: ReactNode;
  node?: unknown;
  sources?: ProvenanceItem[];
}) {
  const isNested = useContext(NestedBlockContext);
  if (!isNested && isBoldOnly(node as MarkdownNode | undefined)) {
    const strong = Children.toArray(children).find(isValidElement) as
      | ReactElement<{ children?: ReactNode }>
      | undefined;
    return (
      <h4 className={HEADING_3_CLASS}>
        {renderWithCitations(strong?.props.children, sources)}
      </h4>
    );
  }
  return (
    <p className="text-body-large mb-3 last:mb-0">
      {renderWithCitations(children, sources)}
    </p>
  );
}

/** True inside code and links, whose text renders verbatim: no citation chips. */
const PlainTextContext = createContext(false);

/** A word span from rehypeStreamWords, with citations unless inside plain text. */
function StreamSpan({
  children,
  className,
  style,
  sources,
}: {
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  sources?: ProvenanceItem[];
}) {
  const isPlainText = useContext(PlainTextContext);
  return (
    <span className={className} style={style}>
      {isPlainText ? children : renderWithCitations(children, sources)}
    </span>
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
      {/* Same frame as a chart tile. The cells' outer borders are dropped so
          they do not double up with the frame's. */}
      <div className="overflow-x-auto mb-3 border border-border rounded-chart bg-surface">
        <table
          className="min-w-full text-sm border-collapse [&_tr>*:first-child]:border-l-0 [&_tr>*:last-child]:border-r-0 [&_thead_tr:first-child>*]:border-t-0 [&_tbody_tr:last-child>*]:border-b-0"
          style={style}
        >
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
      // An explicit markdown alignment arrives in `style` and wins over the
      // class.
      className={`border border-outline px-6 pb-2 pt-3 font-medium ${
        numeric ? 'text-right' : 'text-left'
      }`}
      style={style}
    >
      {renderWithCitations(children, sources)}
      {toAppend.map((n) => (
        <span key={n}>
          {' '}
          <CitationChip n={n} sources={sources} />
        </span>
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
      // An explicit markdown alignment arrives in `style` and wins over the
      // class.
      className={`border border-outline px-6 py-2${
        numeric ? ' tabular-nums text-right' : ''
      }`}
      style={style}
    >
      <HideCitationsProvider value={hoisted}>
        {renderWithCitations(children, sources)}
      </HideCitationsProvider>
    </td>
  );
}
