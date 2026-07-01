/**
 * @fileoverview Compact footer list of sources — the import_name +
 * provenance_url pairs extracted from get_observations source_metadata by the
 * agent backend.
 */

import type { ProvenanceItem } from "../hooks/use_sse_chat";

interface FooterSourcesProps {
  sources: ProvenanceItem[];
}

/**
 * Renders the footer-style sources list. Returns nothing when there are no
 * sources.
 */
export function FooterSources({ sources }: FooterSourcesProps) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-1">
      <h4 className="text-title-large-emphasized">Sources</h4>
      <ul className="text-body-large text-on-surface list-none flex flex-col gap-1">
        {sources.map((source, index) => (
          <li key={index}>
            <span className="text-on-surface-variant">[{index + 1}]</span>{" "}
            {source.url ? (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-brand-primary-dark"
              >
                {source.name || source.url}
              </a>
            ) : (
              source.name || "Source"
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
