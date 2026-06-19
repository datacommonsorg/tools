interface SkeletonCardProps {
  query: string;
}

export default function SkeletonCard({ query }: SkeletonCardProps) {
  return (
    <div className="w-full border border-gray-200 rounded-[24px] overflow-hidden shadow-sm bg-surface-soft">
      <div className="px-6 py-4 border-b border-gray-100 text-body-large-emphasized text-on-surface bg-white">
        {query}
      </div>
      <div className="px-[56px] py-6 flex flex-col gap-[16px]">

        {/* Paragraph 1 */}
        <div className="flex flex-row gap-4 items-start">
          <div className="w-[1px] h-[72px] bg-line"></div>
          <div className="flex flex-col gap-[8px] flex-1">
            <div className="h-[12px] rounded-[4px] w-[314px] animate-pulse bg-user-msg"></div>
            <div className="h-[12px] rounded-[4px] w-full animate-pulse bg-user-msg"></div>
            <div className="h-[12px] rounded-[4px] w-full animate-pulse bg-user-msg"></div>
            <div className="h-[12px] rounded-[4px] w-[400px] animate-pulse bg-user-msg"></div>
          </div>
        </div>

        {/* Paragraph 2 */}
        <div className="flex flex-row gap-4 items-start">
          <div className="w-[1px] h-[72px] bg-line"></div>
          <div className="flex flex-col gap-[8px] flex-1">
            <div className="h-[12px] rounded-[4px] w-[314px] animate-pulse bg-user-msg"></div>
            <div className="h-[12px] rounded-[4px] w-full animate-pulse bg-user-msg"></div>
            <div className="h-[12px] rounded-[4px] w-full animate-pulse bg-user-msg"></div>
            <div className="h-[12px] rounded-[4px] w-[400px] animate-pulse bg-user-msg"></div>
          </div>
        </div>
      </div>
    </div>
  );
}
