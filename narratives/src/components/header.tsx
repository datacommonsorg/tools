/**
 * @fileoverview Renders the top navigation header: brand logo and the primary nav tabs.
 */

import { ChevronDown } from "lucide-react";
import { MenuIcon } from "./Icons";
import { NAV_CONFIG } from "../config/nav_config";
import { useHashRoute } from "../hooks/use_hash_route";
import { useChatSession } from "../hooks/chat_session_context";
import { useBrand } from "../hooks/branding_context";

/** Renders the brand logo and the primary navigation tabs. */
export function Header() {
  const [route] = useHashRoute();
  const { logoUrl, instanceName } = useBrand();
  // Empty route → Agent (the default landing view).
  const activeId = route || "agent";
  // The hamburger only drives the chat-sessions drawer, which is an
  // Agent-tab concept — match the old Sidebar's `isAgent` gating.
  const isAgent = route === "" || route === "agent";
  const { toggleDrawer, isDrawerOpen } = useChatSession();

  return (
    <header className="w-full flex items-center justify-between gap-3 px-3 sm:px-6 lg:px-12 py-4 sm:py-5 shrink-0">
      {/* Logo Section */}
      <div className="flex items-center select-none shrink-0">
        <img
          src={logoUrl || "/logo.png"}
          alt={`${instanceName || "People + AI"} logo`}
          className="h-8 sm:h-10 object-contain"
        />
      </div>

      {/* Right Navigation — horizontally scrollable on narrow screens so all
          tabs remain reachable without crowding the logo. */}
      <nav className="flex items-center gap-4 md:gap-6 lg:gap-8 text-label-large text-on-surface-variant ml-auto whitespace-nowrap overflow-x-auto no-scrollbar">
        {NAV_CONFIG.map((item) => {
          const isActive = item.id === activeId;
          return (
            <a
              key={item.id}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`relative py-1 shrink-0 transition-colors ${
                isActive ? "font-medium text-brand-primary" : "hover:text-on-surface"
              }`}
            >
              {item.label}
              {isActive && (
                <span className="absolute top-0 left-0 w-full h-0.5 rounded-b-sm bg-brand-primary" />
              )}
            </a>
          );
        })}

        <div className="hidden sm:block h-4 w-px bg-gray-300 mx-1 shrink-0"></div>

        {/* TODO(i18n): language is hardcoded to English; move to branding config
            or wire up localization before exposing more languages. */}
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={false}
          className="hidden sm:flex items-center gap-1 hover:text-on-surface transition-colors font-medium shrink-0"
        >
          English
          <ChevronDown size={16} className="mt-0.5 text-on-surface-variant" strokeWidth={2} />
        </button>
      </nav>

      {/* Mobile hamburger — replaces the static left rail below `lg`. Opens
          the chat-sessions panel from the left. Sits at the far-right corner
          of the header per design; hidden on desktop where the rail exists. */}
      {isAgent && (
        <button
          type="button"
          aria-label="Open menu"
          aria-expanded={isDrawerOpen}
          onClick={toggleDrawer}
          className={`lg:hidden shrink-0 ml-1 w-10 h-10 flex items-center justify-center rounded-full transition-colors ${
            isDrawerOpen
              ? "bg-button-hover text-on-surface"
              : "hover:bg-button-hover text-on-surface-variant"
          }`}
        >
          <MenuIcon size={24} />
        </button>
      )}
    </header>
  );
}
