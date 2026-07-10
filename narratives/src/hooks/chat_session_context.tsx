/**
 * @fileoverview Provides a React context managing multi-session chat state and the shared streaming machine.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  useSseChat,
  type ChatTurn,
  type UseSseChatResult,
} from "./use_sse_chat";

/**
 * "Persistent questions per session — multiple threads, lightweight tracking,
 * duration-of-the-session, no formal sign-up" (client spec).
 *
 * Data model: a flat array of ChatSession objects, each with its own turns
 * and (optional) server-side session_id. The active session is identified by
 * `currentId`. localStorage envelope is versioned (`cdc:chat:v2`) and
 * migrates a single v1 transcript into one session if found, so users don't
 * lose chat history across the upgrade.
 *
 * useSseChat is now controlled — turns and sessionId come from props. The
 * provider plumbs them in from whichever session is current. Switching
 * sessions is just a `currentId` change; the same useSseChat instance keeps
 * running, now wired to the new session's turns.
 */

const STORAGE_KEY = "cdc:chat:v2";
const LEGACY_STORAGE_KEY = "cdc:chat:v1";

/** One saved chat thread: its turns plus list-ordering metadata. */
export interface ChatSession {
  id: string; // local UUID — not the server's session id
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: ChatTurn[];
  serverSessionId?: string;
}

/** In-memory session store: all saved sessions plus the active one. */
interface ChatSessionStore {
  sessions: ChatSession[]; // ordered by updatedAt desc — newest first
  currentId: string;
}

/** Everything the chat surface needs: streaming controls + session management. */
export interface ChatSessionContextValue extends UseSseChatResult {
  // Current session's chat surface — same shape DataAgent has always used.
  turns: ChatTurn[];

  // Multi-session management.
  sessions: ChatSession[];
  currentSessionId: string;
  switchSession: (id: string) => void;
  newSession: () => void;
  deleteSession: (id: string) => void;

  // UI state for the session drawer (controlled by Sidebar's menu icon).
  isDrawerOpen: boolean;
  toggleDrawer: () => void;
  closeDrawer: () => void;
}

/** localStorage wire format (v2): the whole store, versioned for migration. */
interface PersistedV2 {
  version: 2;
  sessions: ChatSession[];
  currentId: string;
}

/** Generates a local session id (crypto.randomUUID with a fallback). */
function genId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for very old browsers.
  return `s_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

/** Creates a fresh, empty chat session stamped with the current time. */
function emptySession(): ChatSession {
  const now = Date.now();
  return {
    id: genId(),
    title: "New chat",
    createdAt: now,
    updatedAt: now,
    turns: [],
  };
}

/**
 * Drop turns that were mid-stream when the page closed — their SSE source is
 * dead, they'll never resolve. Same defensive cleaning as v1.
 */
function cleanTurns(turns: ChatTurn[]): ChatTurn[] {
  if (!Array.isArray(turns)) return [];
  return turns.filter(
    (t) => t && (t.status === "done" || t.status === "error"),
  );
}

/** Migrates a legacy v1 single-transcript localStorage entry into one session. */
function migrateV1(): ChatSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) return null;
    const v1 = JSON.parse(raw) as {
      version?: number;
      turns?: ChatTurn[];
      sessionId?: string;
    };
    const turns = cleanTurns(v1.turns ?? []);
    if (turns.length === 0) {
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
      return null;
    }
    const now = Date.now();
    const session: ChatSession = {
      id: genId(),
      title: deriveTitle(turns),
      createdAt: now,
      updatedAt: now,
      turns,
      serverSessionId: v1.sessionId,
    };
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    return session;
  } catch {
    return null;
  }
}

/** Loads the session store from localStorage, migrating v1 data if present. */
function loadPersisted(): ChatSessionStore {
  if (typeof window === "undefined") {
    const sess = emptySession();
    return { sessions: [sess], currentId: sess.id };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as PersistedV2;
      if (parsed.version === 2 && Array.isArray(parsed.sessions)) {
        const cleaned = parsed.sessions
          .map((session) => ({ ...session, turns: cleanTurns(session.turns) }))
          .filter((session) => session.id);
        // Collapse stale empty sessions left over from earlier visits down
        // to at most one. Keeps the drawer tidy for users who accumulated
        // empties before the dedup logic shipped.
        const nonEmpty = cleaned.filter((session) => session.turns.length > 0);
        const empties = cleaned.filter((session) => session.turns.length === 0);
        const collapsed =
          empties.length > 0
            ? [...nonEmpty, empties[0]]
            : nonEmpty;
        if (collapsed.length > 0) {
          const currentId = collapsed.some(
            (session) => session.id === parsed.currentId,
          )
            ? parsed.currentId
            : collapsed[0].id;
          return { sessions: collapsed, currentId };
        }
      }
    }
    // No v2 — try migrating from v1.
    const migrated = migrateV1();
    if (migrated) {
      return { sessions: [migrated], currentId: migrated.id };
    }
  } catch {
    /* fall through */
  }
  // First run / corrupted storage — seed with one empty session.
  const sess = emptySession();
  return { sessions: [sess], currentId: sess.id };
}

/** Writes the session store to localStorage; failures are non-fatal. */
function persist(store: ChatSessionStore): void {
  if (typeof window === "undefined") return;
  try {
    const payload: PersistedV2 = {
      version: 2,
      sessions: store.sessions,
      currentId: store.currentId,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // QuotaExceededError or storage disabled — fail silently.
  }
}

/** Derives a short drawer title from the session's first user message. */
function deriveTitle(turns: ChatTurn[]): string {
  const first = turns[0]?.userMessage?.trim();
  if (!first) return "New chat";
  return first.length > 60 ? first.slice(0, 60) + "…" : first;
}

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

/**
 * Owns the session store (persisted to localStorage) and the single
 * streaming machine, exposing both to the tree via context.
 */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<ChatSessionStore>(loadPersisted);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // Persist whenever the store changes. Skipped for the initial render in
  // some setups because `store` from loadPersisted is reference-equal to the
  // first useState value — but writing it once on mount is harmless.
  useEffect(() => {
    persist(store);
  }, [store]);

  // Find the current session. Guaranteed non-null because loadPersisted seeds
  // an empty one when nothing exists. If somehow currentId points at a
  // missing session (e.g., stale tab after delete in another tab), fall back
  // to sessions[0].
  const currentSession =
    store.sessions.find((session) => session.id === store.currentId) ??
    store.sessions[0];

  const turns = currentSession.turns;
  const sessionId = currentSession.serverSessionId;

  // Controlled setters into the current session's slot.
  const setTurns = useCallback(
    (updater: (prev: ChatTurn[]) => ChatTurn[]) => {
      setStore((prev) => {
        const idx = prev.sessions.findIndex((s) => s.id === prev.currentId);
        if (idx < 0) return prev;
        const nextTurns = updater(prev.sessions[idx].turns);
        if (nextTurns === prev.sessions[idx].turns) return prev;
        const sessions = prev.sessions.slice();
        const oldTitle = sessions[idx].title;
        const newTitle =
          oldTitle === "New chat" || !oldTitle
            ? deriveTitle(nextTurns)
            : oldTitle;
        sessions[idx] = {
          ...sessions[idx],
          turns: nextTurns,
          updatedAt: Date.now(),
          title: newTitle,
        };
        return { ...prev, sessions };
      });
    },
    [],
  );

  const setSessionId = useCallback((id: string | undefined) => {
    setStore((prev) => {
      const idx = prev.sessions.findIndex((s) => s.id === prev.currentId);
      if (idx < 0) return prev;
      if (prev.sessions[idx].serverSessionId === id) return prev;
      const sessions = prev.sessions.slice();
      sessions[idx] = { ...sessions[idx], serverSessionId: id };
      return { ...prev, sessions };
    });
  }, []);

  const { isStreaming, error, send, stop } = useSseChat({
    turns,
    setTurns,
    sessionId,
    setSessionId,
  });

  // ---- multi-session controls ----

  const newSession = useCallback(() => {
    setStore((prev) => {
      // If there's already an empty session in the store, reuse it rather
      // than create a second one. Keeps the drawer free of stale "New chat"
      // rows when the user repeatedly clicks "+ New" or bounces between
      // tabs (ChatResetOnTabChange also funnels through here).
      const existingEmpty = prev.sessions.find(
        (session) => session.turns.length === 0,
      );
      if (existingEmpty) {
        if (prev.currentId === existingEmpty.id) return prev;
        return { ...prev, currentId: existingEmpty.id };
      }
      const sess = emptySession();
      return {
        sessions: [sess, ...prev.sessions],
        currentId: sess.id,
      };
    });
    setIsDrawerOpen(false);
  }, []);

  const switchSession = useCallback((id: string) => {
    setStore((prev) => {
      if (!prev.sessions.some((session) => session.id === id)) return prev;
      if (prev.currentId === id) return prev;
      return { ...prev, currentId: id };
    });
    setIsDrawerOpen(false);
  }, []);

  const deleteSession = useCallback((id: string) => {
    setStore((prev) => {
      const remaining = prev.sessions.filter((session) => session.id !== id);
      if (remaining.length === prev.sessions.length) return prev;
      let nextCurrent = prev.currentId;
      if (nextCurrent === id) {
        nextCurrent = remaining[0]?.id ?? "";
      }
      // Never end up with an empty list — seed a new empty session.
      if (remaining.length === 0) {
        const sess = emptySession();
        return { sessions: [sess], currentId: sess.id };
      }
      return { sessions: remaining, currentId: nextCurrent };
    });
  }, []);

  const toggleDrawer = useCallback(() => setIsDrawerOpen((v) => !v), []);
  const closeDrawer = useCallback(() => setIsDrawerOpen(false), []);

  // Sessions list passed to consumers is sorted newest-updated first.
  const sortedSessions = useMemo(
    () => store.sessions.slice().sort((a, b) => b.updatedAt - a.updatedAt),
    [store.sessions],
  );

  const value: ChatSessionContextValue = useMemo(
    () => ({
      // current session view
      turns,
      isStreaming,
      error,
      send,
      stop,
      // multi-session
      sessions: sortedSessions,
      currentSessionId: currentSession.id,
      switchSession,
      newSession,
      deleteSession,
      // drawer UI
      isDrawerOpen,
      toggleDrawer,
      closeDrawer,
    }),
    [
      turns,
      isStreaming,
      error,
      send,
      stop,
      sortedSessions,
      currentSession.id,
      switchSession,
      newSession,
      deleteSession,
      isDrawerOpen,
      toggleDrawer,
      closeDrawer,
    ],
  );

  return (
    <ChatSessionContext.Provider value={value}>
      {children}
    </ChatSessionContext.Provider>
  );
}

/** Returns the chat session context; must be used under ChatSessionProvider. */
export function useChatSession(): ChatSessionContextValue {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) {
    throw new Error(
      "useChatSession must be used inside a ChatSessionProvider",
    );
  }
  return ctx;
}

const MS_PER_MINUTE = 60_000;
const MS_PER_HOUR = 60 * MS_PER_MINUTE;
const MS_PER_DAY = 24 * MS_PER_HOUR;

/**
 * Light helper for the drawer UI. Exported so the drawer can reuse the same
 * relative-time format if we want to tweak it in one place.
 */
export function formatRelativeTime(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < MS_PER_MINUTE) return "just now";
  if (diff < MS_PER_HOUR) return `${Math.floor(diff / MS_PER_MINUTE)} min ago`;
  if (diff < MS_PER_DAY) return `${Math.floor(diff / MS_PER_HOUR)} hr ago`;
  if (diff < 2 * MS_PER_DAY) return "yesterday";
  const days = Math.floor(diff / MS_PER_DAY);
  if (days < 7) return `${days} days ago`;
  return new Date(ts).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
