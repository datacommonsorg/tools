interface SuggestionChipProps {
  text: string;
  onClick?: (text: string) => void;
}

export default function SuggestionChip({ text, onClick }: SuggestionChipProps) {
  return (
    <button
      type="button"
      onClick={() => onClick?.(text)}
      className="w-[250px] min-h-[72px] px-4 py-3 border border-gray-200 rounded-[20px] bg-white hover:bg-gray-50 cursor-pointer transition-all duration-200 text-body-medium text-on-surface flex items-center justify-center sm:justify-start shadow-[0_1px_3px_rgba(0,0,0,0.02)] hover:shadow-md text-left"
    >
      {text}
    </button>
  );
}
