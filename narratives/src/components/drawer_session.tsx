/**
 * @fileoverview Renders the multi-session chat drawer: list, switch, and delete chat sessions.
 */

import { useState, type ReactNode } from "react";
import { Trash2, X, ArrowRight, ArrowLeft } from "lucide-react";
import { NewChatIcon, ChatsIcon } from "./Icons";
import {
  formatRelativeTime,
  useChatSession,
} from "../hooks/chat_session_context";

/**
 * SessionDrawer renders two distinct layouts behind one trigger; only one is
 * visible at a time (Tailwind `lg:` toggles), and they share session data:
 *
 *  • Desktop (lg+): a single-level list anchored to the LEFT, flush against
 *    the 72px icon rail (Sidebar). Header = "Chats" + "+ New". Opening it
 *    doesn't shift the rest of the layout (design direction: no layout jump).
 *
 *  • Mobile (<lg): a two-level slide-in panel anchored to the RIGHT (the
 *    hamburger lives at the header's right edge). Level 1 = "New chat" / "Chats"
 *    rows; level 2 = the saved-session list. Both panes live in a 200%-wide
 *    track that translates horizontally between levels.
 */

const DESKTOP_PANEL_WIDTH = 300;
const MOBILE_PANEL_WIDTH = 320;
const SIDEBAR_OFFSET = 72; // desktop rail width (Sidebar.tsx lg:w-[72px])
const FONT_DISPLAY = "var(--font-display)";
/**
 * Menu-item text + leading icons + the ✕ read as secondary, so they use the
 * lighter "subtle" grey; the trailing chevron is the dark accent.
 */
const COLOR_LABEL = "var(--color-subtle)";
const COLOR_ARROW = "var(--color-on-surface)";

/** The chats drawer: desktop left-anchored list and mobile two-level slide-in panel. */
export function SessionDrawer() {
  const {
    sessions,
    currentSessionId,
    switchSession,
    newSession,
    deleteSession,
    isDrawerOpen,
    closeDrawer,
  } = useChatSession();

  // Which level the MOBILE panel is showing. Reset to "menu" whenever the
  // drawer closes so the next open always starts at the top level.
  const [view, setView] = useState<"menu" | "chats">("menu");

  if (!isDrawerOpen) return null;

  const close = () => {
    setView("menu");
    closeDrawer();
  };

  // Hide empty drafts from the history list — the active empty session is
  // already represented by the Data Agent InitialView, so a duplicate row
  // here just looks like clutter ("New chat", "New chat", "New chat").
  const visibleSessions = sessions.filter(
    (session) => session.turns.length > 0,
  );

  const handleNewChat = () => {
    newSession();
    close();
  };

  return (
    <>
      {/* Click-outside backdrop. Dimmed on mobile (the drawer floats over
          full-width content); transparent on desktop where it just needs a
          click capture. */}
      <div
        className="fixed inset-0 z-10 bg-black/30 lg:bg-transparent"
        onClick={close}
        aria-hidden="true"
      />

      {/* ─── Desktop: single-level list, anchored left beside the rail ─── */}
      <aside
        className="hidden lg:flex absolute top-0 left-[72px] h-full bg-white border-r border-gray-200 shadow-lg z-20 flex-col"
        style={{
          // Cap at PANEL_WIDTH, but never exceed the viewport left of the rail.
          width: `min(${DESKTOP_PANEL_WIDTH}px, calc(100vw - ${SIDEBAR_OFFSET}px))`,
        }}
        aria-label="Chat sessions"
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2
            className="m-0"
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 16,
              lineHeight: "24px",
              fontWeight: 500,
              color: COLOR_ARROW,
            }}
          >
            Chats
          </h2>
        </header>

        <SessionList
          sessions={visibleSessions}
          currentSessionId={currentSessionId}
          // Desktop panel is persistent — switching keeps it open.
          onSelect={(id) => switchSession(id)}
          onDelete={deleteSession}
        />
      </aside>

      {/* ─── Mobile: two-level slide-in panel, anchored right ─── */}
      <aside
        className="lg:hidden absolute top-0 right-0 h-full bg-white border-l border-gray-200 shadow-lg z-20 overflow-hidden"
        style={{
          // Cap at PANEL_WIDTH but always leave a peek of the content behind.
          width: `min(${MOBILE_PANEL_WIDTH}px, calc(100vw - 48px))`,
        }}
        aria-label="Menu"
      >
        {/* Two-pane sliding track: 200% wide, shifted -50% to reveal the chats
            pane. The transition animates both directions (forward + back). */}
        <div
          className="flex h-full w-[200%] transition-transform duration-300 ease-in-out"
          style={{
            transform: view === "chats" ? "translateX(-50%)" : "translateX(0)",
          }}
        >
          {/* ── Level 1: menu ─────────────────────────────────────────── */}
          <div className="w-1/2 h-full flex flex-col">
            {/* Close (✕) — top-right corner. */}
            <div className="flex items-center justify-end px-2 py-2 shrink-0">
              <button
                type="button"
                aria-label="Close menu"
                onClick={close}
                className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors"
                style={{ color: COLOR_LABEL }}
              >
                <X size={24} strokeWidth={1.5} />
              </button>
            </div>

            <div className="border-t border-gray-200 shrink-0" />

            <nav className="flex flex-col py-2 shrink-0">
              <MenuItem
                icon={<NewChatIcon size={22} />}
                label="New chat"
                onClick={handleNewChat}
              />
              <MenuItem
                icon={<ChatsIcon size={22} />}
                label="Chats"
                onClick={() => setView("chats")}
              />
            </nav>
          </div>

          {/* ── Level 2: chats ────────────────────────────────────────── */}
          <div className="w-1/2 h-full flex flex-col">
            {/* Header: back arrow + "Chats". */}
            <div className="flex items-center gap-2 px-2 py-2 shrink-0">
              <button
                type="button"
                aria-label="Back"
                onClick={() => setView("menu")}
                className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors"
                style={{ color: COLOR_ARROW }}
              >
                <ArrowLeft size={22} strokeWidth={1.5} />
              </button>
              <h2
                className="m-0"
                style={{
                  fontFamily: FONT_DISPLAY,
                  fontSize: 16,
                  lineHeight: "24px",
                  fontWeight: 500,
                  color: COLOR_ARROW,
                }}
              >
                Chats
              </h2>
            </div>

            <div className="border-t border-gray-200 shrink-0" />

            <SessionList
              sessions={visibleSessions}
              currentSessionId={currentSessionId}
              // Mobile drawer closes after a pick, like a typical sheet.
              onSelect={(id) => {
                switchSession(id);
                close();
              }}
              onDelete={deleteSession}
            />
          </div>
        </div>
      </aside>
    </>
  );
}

/**
 * The saved-session list, shared by both layouts. `onSelect` differs per
 * layout (desktop stays open, mobile closes); everything else is identical.
 */
function SessionList({
  sessions,
  currentSessionId,
  onSelect,
  onDelete,
}: Readonly<{
  sessions: ReturnType<typeof useChatSession>["sessions"];
  currentSessionId: string;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}>) {
  return (
    <ul className="flex-1 overflow-y-auto no-scrollbar list-none p-0 m-0">
      {sessions.map((session) => {
        const active = session.id === currentSessionId;
        return (
          <li
            key={session.id}
            className={`group relative flex items-start gap-2 px-4 py-3 border-b border-gray-50 cursor-pointer transition-colors ${
              active ? "bg-surface-blue" : "hover:bg-gray-50"
            }`}
            onClick={() => onSelect(session.id)}
          >
            <div className="flex-1 min-w-0">
              <div
                className="truncate"
                style={{
                  fontFamily: FONT_DISPLAY,
                  fontSize: 14,
                  lineHeight: "20px",
                  fontWeight: active ? 500 : 400,
                  color: "var(--color-on-surface)",
                }}
                title={session.title}
              >
                {session.title}
              </div>
              <div className="text-caption text-subtle mt-1">
                {formatRelativeTime(session.updatedAt)}
                {session.turns.length > 0 && (
                  <>
                    {" · "}
                    {session.turns.length}{" "}
                    {session.turns.length === 1 ? "message" : "messages"}
                  </>
                )}
              </div>
            </div>
            {/* Delete on hover; don't propagate click so we don't switch into
                the session we're deleting. */}
            <button
              type="button"
              aria-label={`Delete chat: ${session.title}`}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(session.id);
              }}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-on-surface-variant hover:text-red-600 p-1"
            >
              <Trash2 size={16} strokeWidth={1.5} />
            </button>
          </li>
        );
      })}
      {sessions.length === 0 && (
        <li className="px-4 py-6 text-body-medium text-subtle text-center">
          No chats yet.
        </li>
      )}
    </ul>
  );
}

/**
 * A single tappable row in the mobile level-1 menu: leading icon + label on
 * the left, a dark trailing chevron on the right. The whole row is the button.
 */
function MenuItem({
  icon,
  label,
  onClick,
}: Readonly<{
  icon: ReactNode;
  label: string;
  onClick: () => void;
}>) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left bg-transparent border-0 cursor-pointer hover:bg-gray-50 transition-colors"
    >
      <span className="flex items-center gap-3" style={{ color: COLOR_LABEL }}>
        {icon}
        <span
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 15,
            lineHeight: "20px",
            fontWeight: 500,
          }}
        >
          {label}
        </span>
      </span>
      <ArrowRight size={20} strokeWidth={1.5} style={{ color: COLOR_ARROW }} />
    </button>
  );
}
