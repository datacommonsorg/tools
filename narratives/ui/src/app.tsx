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
 * @fileoverview Root application component: wires providers, the sidebar/header/main layout, and hash-routed views.
 */

import { useEffect, useRef } from 'react';
import { DataAgent } from './components/data_agent';
import { DataDownloadTool } from './components/data_download_tool';
import { SessionDrawer } from './components/drawer_session';
import { Header } from './components/header';
import { MetricsPage } from './components/metrics_page';
import { Sidebar } from './components/sidebar';
import { StatVarExplorer } from './components/stat_var_explorer';
import {
  ChatSessionProvider,
  useChatSession,
} from './hooks/chat_session_context';
import { useHashRoute } from './hooks/use_hash_route';

/** Picks the main view for the current hash route; unknown routes fall back to the Data Agent. */
function renderContent(route: string) {
  switch (route) {
    case 'metrics':
      return <MetricsPage />;
    case 'download':
      return <DataDownloadTool />;
    case 'statvar':
      return <StatVarExplorer />;
    default:
      return <DataAgent />;
  }
}

/** Root component: providers + sidebar/header layout around the routed view. */
export function App() {
  const [route] = useHashRoute();

  return (
    <ChatSessionProvider>
      <ChatResetOnTabChange route={route} />
      <div className="flex h-screen w-full bg-surface overflow-hidden relative">
        <Sidebar />
        <SessionDrawer />
        <main className="flex-1 flex flex-col h-full relative min-w-0">
          <Header />
          {renderContent(route)}
        </main>
      </div>
    </ChatSessionProvider>
  );
}

/**
 * Switching tabs (Data Agent ↔ Metrics ↔ StatVar) should land the user on a
 * fresh Data Agent surface, not the previous conversation. The old chat is
 * preserved in the session drawer; we just rotate to a new empty session so
 * the next return to / starts clean. Skip when streaming so a tab-bounce mid
 * answer doesn't orphan the in-flight turn.
 */
function ChatResetOnTabChange({ route }: { route: string }) {
  const { turns, isStreaming, newSession } = useChatSession();
  const prevRoute = useRef<string>(route);
  useEffect(() => {
    if (prevRoute.current === route) return;
    prevRoute.current = route;
    if (turns.length > 0 && !isStreaming) {
      newSession();
    }
  }, [route, turns.length, isStreaming, newSession]);
  return null;
}
