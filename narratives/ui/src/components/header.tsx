/**
 * @fileoverview Renders the top navigation header: brand logo and the primary nav tabs.
 */

import { MenuIcon } from "./icons";
import { Tooltip } from "./tooltip";
import { resolveNavItems } from "../config/nav_config";
import { useHashRoute } from "../hooks/use_hash_route";
import { useChatSession } from "../hooks/chat_session_context";
import type { TokenUsage } from "../hooks/use_sse_chat";
import { useBrand } from "../hooks/branding_context";

/**
 * Reports whether the temporary token-usage readout is enabled — i.e. the page
 * was opened with `?debug=tokens`. Evaluated per render (not at module load) so
 * it reacts to client-side navigation and stays safe under SSR/tests.
 */
const isTokenDebugEnabled = () =>
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("debug") === "tokens";

/** Renders the brand logo and the primary navigation tabs. */
export function Header() {
  const [route] = useHashRoute();
  const { logoUrl, logoText, instanceName, navigation } = useBrand();
  const navItems = resolveNavItems(navigation);
  // Empty route → Agent (the default landing view).
  const activeId = route || "agent";
  const { toggleDrawer, isDrawerOpen, turns } = useChatSession();

  // Latest turn that reported usage wins (later turns override earlier ones).
  const latestUsage = isTokenDebugEnabled()
    ? turns.reduce<TokenUsage | undefined>((acc, turn) => turn.usage ?? acc, undefined)
    : undefined;

  return (
    <header className="w-full flex items-center justify-between gap-3 px-3 sm:px-6 lg:px-12 py-4 sm:py-5 shrink-0">
      {/* Logo Section */}
      <div className="flex items-center gap-2 select-none shrink-0">
        {/* branding.json's logo wins; the bundled Data Commons mark is the
            fallback when an instance ships none. */}
        <img
          src={logoUrl || "/dc-logo.svg"}
          alt={`${instanceName || "Data Commons"} logo`}
          className="w-auto object-contain"
          style={{ height: "var(--logo-height)" }}
        />
        {/* Wordmark beside the logo. Rendered only when branding.json supplies
            `logo_text`; an instance whose logo already contains its name omits
            the key and gets the mark alone. */}
        {logoText && (
          <span className="text-body-large-emphasized text-on-surface whitespace-nowrap">
            {logoText}
          </span>
        )}
      </div>

      {/* Temporary token-usage readout (only under ?debug=tokens). Sits between
          the logo and the nav; shows the most recent query's Gemini usage so we
          can gauge per-query cost. Not part of the shipped product UI. */}
      {latestUsage && (
        <div
          className="hidden sm:block text-caption text-on-surface-variant leading-tight border border-outline rounded-md px-3 py-1.5 shrink-0"
          aria-label="Token usage for the latest query"
        >
          <div>Tokens IN: {latestUsage.input.toLocaleString()}</div>
          <div>Tokens OUT: {latestUsage.output.toLocaleString()}</div>
          <div>Total: {latestUsage.total.toLocaleString()}</div>
        </div>
      )}

      {/* Right Navigation — horizontally scrollable on narrow screens so all
          tabs remain reachable without crowding the logo. */}
      <nav className="flex items-center gap-4 md:gap-6 lg:gap-8 text-label-large text-on-surface-variant ml-auto whitespace-nowrap overflow-x-auto no-scrollbar">
        {navItems.map((item) => {
          const isActive = item.id === activeId;
          return (
            <a
              key={item.id}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              // Hidden below lg — on mobile these tabs live in the side drawer
              // (SessionDrawer) instead, so the header nav stays uncluttered.
              className={`relative py-1 shrink-0 transition-colors hidden lg:block ${
                isActive ? "font-medium text-nav-active" : "hover:text-on-surface"
              }`}
            >
              {item.label}
              {isActive && (
                <span className="absolute top-0 left-0 w-full h-0.5 rounded-b-sm bg-nav-active" />
              )}
            </a>
          );
        })}
      </nav>

      {/* Mobile hamburger — replaces the static left rail below `lg`. Opens
          the menu drawer (section tabs + chat controls) from the right. Shown
          on every tab, not just Agent, so the section nav inside the drawer is
          reachable from all views; hidden on desktop where the rail exists. */}
      <Tooltip label="Menu" placement="bottom">
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
        <MenuIcon size="lg" />
      </button>
      </Tooltip>
    </header>
  );
}
