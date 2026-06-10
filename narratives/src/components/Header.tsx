import { ChevronDown } from "lucide-react";
import { navConfig } from "../config/navConfig";
import { useHashRoute } from "../hooks/useHashRoute";

export default function Header() {
  const [route] = useHashRoute();
  // Empty route → Agent (the default landing view).
  const activeId = route || "agent";

  return (
    <header className="w-full flex items-center justify-between px-6 lg:px-12 py-5 shrink-0 whitespace-nowrap overflow-x-auto">
      {/* Logo Section */}
      <div className="flex items-center select-none">
        <img src="/logo.png" alt="People + AI Logo" className="h-10 object-contain" />
      </div>

      {/* Right Navigation */}
      <nav className="flex items-center gap-8 text-label-large text-on-surface-variant ml-auto">
        {navConfig.map((item) => (
          item.id === activeId ? (
            <div key={item.id} className="relative cursor-pointer group py-1">
              <span className="font-medium text-teal">{item.label}</span>
              <div className="absolute top-0 left-0 w-full h-[3px] rounded-b-sm bg-teal"></div>
            </div>
          ) : (
            <a key={item.id} href={item.href} className="hover:text-on-surface transition-colors">{item.label}</a>
          )
        ))}

        <div className="h-4 w-[1px] bg-gray-300 mx-1"></div>

        <button className="flex items-center gap-1 hover:text-on-surface transition-colors font-medium">
          English
          <ChevronDown size={16} className="mt-[2px] text-on-surface-variant" strokeWidth={2} />
        </button>
      </nav>
    </header>
  );
}
