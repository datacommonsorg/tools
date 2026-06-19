import React from "react";
import { ChevronDown } from "lucide-react";
import { NAV_CONFIG } from "../config/navConfig";
import { useHashRoute } from "../hooks/useHashRoute";
import { useBrand } from "../hooks/BrandingContext";

/**
 * Header component rendering the brand logo and the horizontal navigation menu.
 */
export function Header() {
  const [route] = useHashRoute();
  const { logoUrl, instanceName } = useBrand();
  // Empty route → Agent (the default landing view).
  const activeId = route || "agent";

  return (
    <header className="w-full flex items-center justify-between px-6 lg:px-12 py-5 shrink-0 overflow-hidden">
      {/* Logo Section */}
      <div className="flex items-center select-none shrink-0 mr-4">
        <img
          src={logoUrl || "/logo.png"}
          alt={`${instanceName || "People + AI"} Logo`}
          className="h-10 object-contain"
        />
      </div>

      {/* Right Navigation */}
      <nav className="flex items-center gap-8 text-label-large text-on-surface-variant ml-auto overflow-x-auto whitespace-nowrap scrollbar-none py-1">
        {NAV_CONFIG.map((item) => {
          const isActive = item.id === activeId;
          return (
            <a
              key={item.id}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`relative py-1 transition-colors ${
                isActive ? "font-medium text-teal" : "hover:text-on-surface"
              }`}
            >
              {item.label}
              {isActive && (
                <div className="absolute top-0 left-0 w-full h-0.5 rounded-b-sm bg-teal"></div>
              )}
            </a>
          );
        })}

        <div className="h-4 w-px bg-gray-300 mx-1"></div>

        {/* TODO(i18n): Language is currently hardcoded to English. Move this configuration to dynamic branding options or configure localization support. */}
        {/* TODO(a11y): Add aria-haspopup="listbox" and aria-expanded when language selection dropdown is implemented. */}
        <button className="flex items-center gap-1 hover:text-on-surface transition-colors font-medium">
          English
          <ChevronDown size={16} className="mt-0.5 text-on-surface-variant" strokeWidth={2} />
        </button>
      </nav>
    </header>
  );
}
