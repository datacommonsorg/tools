/**
 * @fileoverview Provides a React context holding the live chat turns and the shared streaming machine.
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
 * The conversation lives in memory for as long as the page is open and is
 * never written to storage: a reload, a second tab, or a returning visitor
 * starts from an empty surface, and the device keeps no transcript.
 *
 * useSseChat is controlled: turns come from props. The provider owns them so
 * the chat survives a move to another tab of the app and back, and "New chat"
 * is simply an empty turns array.
 */

/** Keys earlier builds wrote the transcript to. */
const LEGACY_STORAGE_KEYS = ["cdc:chat:v1", "cdc:chat:v2"];

/**
 * Deletes a transcript an earlier build saved on this device. Chats are no
 * longer stored, so without this the old entry would sit in localStorage for
 * good with nothing left that reads it.
 */
function clearStoredChats(): void {
  if (typeof window === "undefined") return;
  try {
    for (const key of LEGACY_STORAGE_KEYS) {
      window.localStorage.removeItem(key);
    }
  } catch {
    // Storage disabled — there is nothing to clear.
  }
}

/** Everything the chat surface needs: the turns plus streaming controls. */
export interface ChatSessionContextValue extends UseSseChatResult {
  turns: ChatTurn[];

  /** Discards the conversation on screen and starts an empty one. */
  newChat: () => void;

  // UI state for the menu drawer (controlled by the header's menu button).
  isDrawerOpen: boolean;
  toggleDrawer: () => void;
  closeDrawer: () => void;
}

/**
 * Exported so a test can render a consumer against a fixed chat state. The
 * application always reaches it through ChatSessionProvider.
 */
export const ChatSessionContext =
  createContext<ChatSessionContextValue | null>(null);

/**
 * Owns the chat turns and the single streaming machine, exposing both to the
 * tree via context.
 */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  useEffect(() => {
    clearStoredChats();
  }, []);

  const { isStreaming, error, send, stop } = useSseChat({ turns, setTurns });

  // Stop first: an answer still streaming belongs to the conversation being
  // discarded, and `send` refuses to open a second stream until it ends.
  const newChat = useCallback(() => {
    stop();
    setTurns([]);
    setIsDrawerOpen(false);
  }, [stop]);

  const toggleDrawer = useCallback(() => setIsDrawerOpen((prev) => !prev), []);
  const closeDrawer = useCallback(() => setIsDrawerOpen(false), []);

  const value: ChatSessionContextValue = useMemo(
    () => ({
      turns,
      isStreaming,
      error,
      send,
      stop,
      newChat,
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
      newChat,
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
