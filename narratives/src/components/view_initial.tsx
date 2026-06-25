import { ChangeEvent, RefObject } from "react";
import ChipSuggestion from "./chip_suggestion";
import { useBrand } from "../hooks/branding_context";

interface ViewInitialProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: () => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}

export default function ViewInitial({ query, setQuery, onSend, textareaRef }: ViewInitialProps) {
  const isExpanded = query.trim().length > 0;
  const brand = useBrand();
  const suggestions = brand.suggestions ?? [];

  return (
    <div className="flex-1 flex flex-col items-center justify-center w-full max-w-5xl mx-auto px-4 lg:px-12 pb-24 relative">

      <h1 className="text-display-small-gradient mb-1 tracking-tight">
        Data Agent
      </h1>
      <p className="text-label-large text-subtle mb-8">
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
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        {/* Action Button */}
        <button
          onClick={onSend}
          className={`w-10 h-10 rounded-full flex items-center justify-center bg-surface-blue hover:bg-button-hover transition-colors shrink-0 group ${
            isExpanded ? "self-end mt-2" : "ml-2"
          }`}
        >
          <img src="/send.png" alt="Send" className="w-7 h-7 object-contain" />
        </button>
      </div>

      {/* Prompt Chips (from branding.json suggestions, fallback DEFAULT_BRAND) */}
      <div className="absolute bottom-6 left-0 right-0 flex flex-wrap justify-center gap-4 px-6">
        {suggestions.map((text, i) => (
          <ChipSuggestion
            key={i}
            text={text}
            onClick={(t) => {
              setQuery(t);
              // Focus the textarea so user can edit / press Enter immediately.
              requestAnimationFrame(() => textareaRef?.current?.focus());
            }}
          />
        ))}
      </div>

    </div>
  );
}
