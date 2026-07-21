/**
 * @fileoverview Renders the desktop left rail: new-chat and chat-history controls.
 */

import { useHashRoute } from "../hooks/use_hash_route";
import { useChatSession } from "../hooks/chat_session_context";
import { NewChatIcon, ChatsIcon } from "./icons";

/**
 * The left rail itself stays visible across all tabs (same width, same fill)
 * so the page layout doesn't jump as the user navigates. Only the two icons
 * (the "accordion" hamburger and the "start new chat" pencil) are tied to
 * the Agent tab; on every other tab the rail renders empty.
 */
export function Sidebar() {
  const [route] = useHashRoute();
  const { newSession, toggleDrawer, isDrawerOpen } = useChatSession();
  const isAgent = route === "" || route === "agent";

  return (
    <aside className="hidden lg:flex w-[72px] h-full bg-surface-blue flex-col items-center py-4 gap-4 shrink-0">
      {isAgent && (
        <>
          {/* Menu / "accordion" icon — toggles the SessionDrawer that lists
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
            <ChatsIcon size="lg" />
          </button>
          {/* Start a fresh chat thread — does NOT delete other sessions; they
              remain accessible from the drawer above. */}
          <button
            type="button"
            aria-label="Start new chat"
            onClick={newSession}
            className="w-12 h-12 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors text-on-surface-variant"
          >
            <NewChatIcon size="md" />
          </button>
        </>
      )}
    </aside>
  );
}
