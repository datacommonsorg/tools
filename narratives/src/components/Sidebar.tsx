import { Menu, SquarePen } from "lucide-react";
import { useHashRoute } from "../hooks/useHashRoute";
import { useChatSession } from "../hooks/ChatSessionContext";

// The left rail itself stays visible across all tabs (same width, same fill)
// so the page layout doesn't jump as the user navigates — per Adriana's
// 23 Apr ¶17 direction. Only the two icons (the "accordion" hamburger and
// the "start new chat" pencil) are tied to the Agent tab; on every other
// tab the rail renders empty.
export default function Sidebar() {
  const [route] = useHashRoute();
  const { newSession, toggleDrawer, isDrawerOpen } = useChatSession();
  const isAgent = route === "" || route === "agent";

  return (
    <aside className="w-[72px] h-full bg-surface-blue flex flex-col items-center py-4 gap-4 shrink-0 border-r border-button-hover lg:border-none">
      {isAgent && (
        <>
          {/* Menu / "accordion" icon — toggles the SessionDrawer that lists
              all chat threads. Adriana referred to this as the accordion in
              23 Apr ¶17. */}
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
          {/* Start a fresh chat thread — does NOT delete other sessions; they
              remain accessible from the drawer above. */}
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
