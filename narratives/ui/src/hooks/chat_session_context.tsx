/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Provides a React context holding the live chat turns and the shared streaming machine.
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  type ChatTurn,
  type UseSseChatResult,
  useSseChat,
} from './use_sse_chat';

/**
 * The conversation is held in memory and never written to storage.
 *
 * useSseChat is controlled: the provider owns the turns, so the chat survives
 * a move to another tab of the app and back.
 */

/** Keys earlier builds wrote the transcript to. */
const LEGACY_STORAGE_KEYS = ['cdc:chat:v1', 'cdc:chat:v2'];

/** Deletes a transcript an earlier build saved; nothing reads it now. */
function clearStoredChats(): void {
  if (typeof window === 'undefined') return;
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
export const ChatSessionContext = createContext<ChatSessionContextValue | null>(
  null,
);

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

  // Stop first: `send` refuses to open a second stream until this one ends.
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
    throw new Error('useChatSession must be used inside a ChatSessionProvider');
  }
  return ctx;
}
