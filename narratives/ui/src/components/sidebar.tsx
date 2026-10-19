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
 * @fileoverview Renders the desktop left rail: the new-chat control.
 */

import { useHashRoute } from "../hooks/use_hash_route";
import { useChatSession } from "../hooks/chat_session_context";
import { NewChatIcon } from "./icons";
import { Tooltip } from "./tooltip";

/**
 * The left rail itself stays visible across all tabs (same width, same fill)
 * so the page layout doesn't jump as the user navigates. Only the "start new
 * chat" pencil is tied to the Agent tab; on every other tab the rail renders
 * empty.
 */
export function Sidebar() {
  const [route] = useHashRoute();
  const { newChat } = useChatSession();
  const isAgent = route === "" || route === "agent";

  return (
    <aside className="hidden lg:flex sticky top-0 w-[72px] h-dvh bg-surface-blue flex-col items-center py-4 gap-4 shrink-0">
      {isAgent && (
        /* Clears the conversation on screen and starts an empty one. Chats
           are not saved, so there is nothing to come back to. */
        <Tooltip label="New Chat" placement="right">
          <button
            type="button"
            aria-label="Start new chat"
            onClick={newChat}
            className="w-12 h-12 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors text-on-surface-variant"
          >
            <NewChatIcon />
          </button>
        </Tooltip>
      )}
    </aside>
  );
}
