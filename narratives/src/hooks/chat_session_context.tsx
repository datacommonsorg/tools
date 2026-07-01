/**
 * @fileoverview React context, provider, and hook for managing chat session
 * state (the list of conversations, the active session, the drawer toggle,
 * and the streaming send action) across the app. Currently a stub provider
 * that wires up the shape without persistence.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";

/** A single message in a conversation, attributed to the user or the model. */
export interface ChatTurn {
  role: "user" | "model";
  text: string;
}

/** A saved conversation thread with its metadata and message history. */
export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: ChatTurn[];
}

/** The full set of state and actions exposed to chat-session consumers. */
export interface ChatSessionContextValue {
  isStreaming: boolean;
  error: string | null;
  send: (message: string) => Promise<void>;
  turns: ChatTurn[];
  sessions: ChatSession[];
  currentSessionId: string;
  switchSession: (id: string) => void;
  newSession: () => void;
  deleteSession: (id: string) => void;
  isDrawerOpen: boolean;
  toggleDrawer: () => void;
  closeDrawer: () => void;
}

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

/**
 * Stub Provider for ChatSession Context.
 */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const value = useMemo<ChatSessionContextValue>(() => ({
    isStreaming: false,
    error: null,
    send: async () => {},
    turns: [],
    sessions: [],
    currentSessionId: "",
    switchSession: () => {},
    newSession: () => {},
    deleteSession: () => {},
    isDrawerOpen: false,
    toggleDrawer: () => {},
    closeDrawer: () => {}
  }), []);

  return (
    <ChatSessionContext.Provider value={value}>
      {children}
    </ChatSessionContext.Provider>
  );
}

/**
 * Stub hook to access the ChatSession context.
 */
export function useChatSession(): ChatSessionContextValue {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) {
    throw new Error("useChatSession must be used inside a ChatSessionProvider");
  }
  return ctx;
}
