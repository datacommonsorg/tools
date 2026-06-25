import React, { createContext, useContext, useMemo, type ReactNode } from "react";

export interface ChatTurn {
  role: "user" | "model";
  text: string;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: ChatTurn[];
}

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
