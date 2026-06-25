import type { ProvenanceItem } from "../hooks/use_sse_chat";

interface FooterSourcesProps {
  sources: ProvenanceItem[];
}

// Renders the list of import_name + provenance_url pairs extracted from
// get_observations source_metadata by the agent backend.
export default function FooterSources({ sources }: FooterSourcesProps) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-1">
      <h4 className="text-title-large-emphasized">Sources</h4>
      <ul className="text-body-large text-on-surface list-none flex flex-col gap-1">
        {sources.map((s, i) => (
          <li key={i}>
            <span className="text-on-surface-variant">[{i + 1}]</span>{" "}
            {s.url ? (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-teal"
              >
                {s.name || s.url}
              </a>
            ) : (
              s.name || "Source"
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
