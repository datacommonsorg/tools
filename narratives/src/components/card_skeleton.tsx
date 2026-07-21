/**
 * @fileoverview Renders the loading skeleton shown while the first answer is prepared.
 */

interface SkeletonCardProps {
  query: string;
}

/** Loading placeholder card shown while the agent works on `query`. */
export function SkeletonCard({ query }: SkeletonCardProps) {
  return (
    <div className="w-full border border-outline rounded-[24px] overflow-hidden shadow-sm bg-surface-soft">
      <div className="px-6 py-4 border-b border-outline-variant text-body-large-emphasized text-on-surface bg-surface">
        {query}
      </div>
      <div className="px-4 sm:px-[56px] py-6 flex flex-col gap-4">

        {/* Paragraph 1 */}
        <div className="flex flex-row gap-4 items-start">
          <div className="w-px h-[72px] bg-line"></div>
          <div className="flex flex-col gap-2 flex-1">
            <div className="h-3 rounded w-full max-w-[314px] animate-pulse bg-user-msg"></div>
            <div className="h-3 rounded w-full animate-pulse bg-user-msg"></div>
            <div className="h-3 rounded w-full animate-pulse bg-user-msg"></div>
            <div className="h-3 rounded w-full max-w-[400px] animate-pulse bg-user-msg"></div>
          </div>
        </div>

        {/* Paragraph 2 */}
        <div className="flex flex-row gap-4 items-start">
          <div className="w-px h-[72px] bg-line"></div>
          <div className="flex flex-col gap-2 flex-1">
            <div className="h-3 rounded w-full max-w-[314px] animate-pulse bg-user-msg"></div>
            <div className="h-3 rounded w-full animate-pulse bg-user-msg"></div>
            <div className="h-3 rounded w-full animate-pulse bg-user-msg"></div>
            <div className="h-3 rounded w-full max-w-[400px] animate-pulse bg-user-msg"></div>
          </div>
        </div>
      </div>
    </div>
  );
}
