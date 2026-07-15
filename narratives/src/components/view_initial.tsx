/**
 * @fileoverview Renders the empty-state landing view: heading, prompt box, and suggestion chips.
 */

import { ChangeEvent, RefObject } from "react";
import { SuggestionChip } from "./chip_suggestion";
import { useBrand } from "../hooks/branding_context";

interface InitialViewProps {
  query: string;
  setQuery: (val: string) => void;
  // Accepts an optional explicit message — used by suggestion chips so the
  // chip text is submitted immediately rather than waiting on a React state
  // update of `query`.
  onSend: (override?: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}

/** Empty-state landing view: hero heading, prompt input, and suggestion chips. */
export function InitialView({ query, setQuery, onSend, textareaRef }: InitialViewProps) {
  const isExpanded = query.trim().length > 0;
  const brand = useBrand();
  const suggestions = brand.suggestions ?? [];

  return (
    <div className="flex-1 flex flex-col items-center justify-start sm:justify-center w-full max-w-5xl mx-auto px-4 lg:px-12 pt-8 sm:pt-0 pb-8 sm:pb-24 relative overflow-y-auto">

      <h1 className="text-display-small-gradient mb-1 tracking-tight text-center">
        Data Agent
      </h1>
      <p className="text-label-large text-subtle mb-8 text-center">
        powered by Google's Data Commons
      </p>

      {/* GM3 Search Box */}
      <div
        className={`w-full max-w-[720px] bg-white border border-gray-200 shadow-[0_2px_12px_rgba(0,0,0,0.06)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.1)] transition-all duration-300 flex ${
          isExpanded
          ? "min-h-[64px] rounded-[24px] flex-col p-4 justify-between"
            : "h-[56px] rounded-full items-center px-4 flex-row"
        }`}
      >
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setQuery(e.target.value)}
          placeholder="Ask a question to explore relevant statistical data"
          className={`bg-transparent w-full outline-none text-body-large text-on-surface placeholder:text-placeholder resize-none overflow-hidden ${isExpanded ? "pl-2 pt-1" : "h-6 leading-6 pl-4"
          }`}
          rows={1}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), onSend())}
        />
        {/* Action Button */}
        <button
          onClick={() => onSend()}
          className={`w-10 h-10 rounded-full flex items-center justify-center bg-surface-blue hover:bg-button-hover transition-colors shrink-0 group ${
            isExpanded ? "self-end mt-2" : "ml-2"
          }`}
        >
          <img src="/send.svg" alt="Send" className="w-6 h-6" />
        </button>
      </div>

      {/* Prompt Chips (from branding.json suggestions, fallback DEFAULT_BRAND).
          On mobile (< sm) we sit inline so the chips don't get clipped under the
          virtual keyboard / browser chrome; from sm: up they dock to the bottom
          of the hero per the Figma spec. */}
      <div className="static sm:absolute sm:bottom-6 sm:left-0 sm:right-0 mt-8 sm:mt-0 w-full flex flex-wrap justify-center gap-3 sm:gap-4 px-2 sm:px-6">
        {suggestions.map((text, index) => (
          <SuggestionChip
            key={index}
            text={text}
            // Clicking a chip submits immediately — saves the user a second
            // click on the send button. We still mirror the text into the
            // input briefly so the question is visible while the request
            // kicks off and the InitialView is replaced by the chat surface.
            onClick={(suggestion) => {
              setQuery(suggestion);
              onSend(suggestion);
            }}
          />
        ))}
      </div>

    </div>
  );
}
