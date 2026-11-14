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

import { NewChatIcon } from '@/src/components/icons';
import { Tooltip } from '@/src/components/tooltip';
import { getRuntimeConfig } from '@/src/config/runtime_config';
import { useChatSession } from '@/src/hooks/chat_session_context';
import { useHashRoute } from '@/src/hooks/use_hash_route';

/**
 * The left rail itself stays visible across all tabs (same width, same fill)
 * so the page layout doesn't jump as the user navigates. The "New chat"
 * pencil renders only on the Agent tab while chat is enabled; otherwise the
 * rail renders empty.
 */
export function Sidebar() {
  const [route] = useHashRoute();
  const { newChat } = useChatSession();
  const { isChatEnabled } = getRuntimeConfig();
  const isAgent = route === '' || route === 'agent';
  const shouldShowNewChat = isAgent && isChatEnabled;

  // The rail is fixed so the header can span the viewport over it. `lg:z-1`
  // lifts it above <main>, whose `lg:pl-rail` padding would otherwise cover
  // it and catch its clicks, and keeps it below the header's `z-5`.
  // `pt-rail-top` grows with `--logo-height` so the header never covers the
  // New chat button.
  return (
    <aside className="hidden lg:flex lg:fixed lg:inset-y-0 lg:left-0 lg:z-1 w-rail bg-surface-blue flex-col items-center pt-rail-top pb-4 gap-4 motion-safe:animate-enter-from-left">
      {shouldShowNewChat && (
        /* Clears the conversation on screen and starts an empty one. Chats
           are not saved, so there is nothing to come back to. */
        <Tooltip label="New chat" placement="right">
          <button
            type="button"
            aria-label="New chat"
            onClick={newChat}
            className="w-12 h-12 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors text-on-surface-variant motion-safe:animate-nudge-from-top"
          >
            <NewChatIcon />
          </button>
        </Tooltip>
      )}
    </aside>
  );
}
