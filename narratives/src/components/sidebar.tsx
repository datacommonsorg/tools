/**
 * @fileoverview Left sidebar navigation rail displaying chat session actions.
 */

import React from "react";
import { Menu, SquarePen } from "lucide-react";
import { useHashRoute } from "../hooks/use_hash_route";
import { useChatSession } from "../hooks/chat_session_context";

/**
 * Sidebar component representing the left rail.
 * Toggles the chat history drawer and initiates new sessions when on the Agent tab.
 */
export function Sidebar() {
  const [route] = useHashRoute();
  const { newSession, toggleDrawer, isDrawerOpen } = useChatSession();
  const isAgent = route === "" || route === "agent";

  return (
    <aside className="w-[72px] h-full bg-surface-blue flex flex-col items-center py-4 gap-4 shrink-0 border-r border-button-hover lg:border-none">
      {isAgent && (
        <>
          {/* Menu / "accordion" icon — toggles the DrawerSession that lists
              all chat threads. */}
          <button
            type="button"
            aria-label="Toggle chats list"
            aria-expanded={isDrawerOpen}
            onClick={toggleDrawer}
            className={`w-12 h-12 flex items-center justify-center rounded-full transition-colors ${
              isDrawerOpen
                ? "bg-button-hover text-on-surface"
                : "hover:bg-button-hover text-on-surface-variant"
            }`}
          >
            <Menu size={24} strokeWidth={1.5} />
          </button>
          {/* Start a fresh chat thread. */}
          <button
            type="button"
            aria-label="Start new chat"
            onClick={newSession}
            className="w-12 h-12 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors text-on-surface-variant"
          >
            <SquarePen size={20} strokeWidth={1.5} />
          </button>
        </>
      )}
    </aside>
  );
}
