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
import { MenuDrawer } from './components/drawer_menu';
import { Header } from './components/header';
import { MetricsPage } from './components/metrics_page';
import { Sidebar } from './components/sidebar';
import {
  ChatSessionProvider,
  useChatSession,
} from './hooks/chat_session_context';
import { useHashRoute } from './hooks/use_hash_route';

/** The main views; every route other than `metrics` shows the Data Agent. */
type View = 'agent' | 'metrics';

/** Gets the view a hash route shows. */
function getView(route: string): View {
  return route === 'metrics' ? 'metrics' : 'agent';
}

/** Renders the main view for the current hash route. */
function renderContent(view: View) {
  switch (view) {
    case 'metrics':
      return <MetricsPage />;
    default:
      return <DataAgent />;
  }
}

/** Root component: providers + sidebar/header layout around the routed view. */
export function App() {
  const [route] = useHashRoute();
  const view = getView(route);

  return (
    <ChatSessionProvider>
      <ChatResetOnTabChange view={view} />
      <div className="flex min-h-dvh w-full bg-surface relative">
        <Sidebar />
        <MenuDrawer />
        <main className="flex-1 flex flex-col relative min-w-0">
          <Header />
          {renderContent(view)}
        </main>
      </div>
    </ChatSessionProvider>
  );
}

/**
 * Switching tabs (Data Agent ↔ Metrics) should land the user on a
 * fresh Data Agent surface, not the previous conversation, so the chat and
 * any answer still streaming are dropped on the way out.
 */
function ChatResetOnTabChange({ view }: { view: View }) {
  const { turns, isStreaming, newChat } = useChatSession();
  const prevView = useRef<View>(view);
  useEffect(() => {
    if (prevView.current === view) return;
    prevView.current = view;
    // Scrolling is managed on the page level, so each view starts at its top.
    window.scrollTo(0, 0);
    if (turns.length > 0 || isStreaming) {
      newChat();
    }
  }, [view, turns.length, isStreaming, newChat]);
  return null;
}
