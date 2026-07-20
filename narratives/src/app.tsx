/**
 * @fileoverview Root application component: wires providers, the sidebar/header/main layout, and hash-routed views.
 */

import { useEffect, useRef } from "react";
import { Sidebar } from "./components/sidebar";
import { Header } from "./components/header";
import { DataAgent } from "./components/data_agent";
import { MetricsPage } from "./components/metrics_page";
import { DataDownloadTool } from "./components/data_download_tool";
import { StatVarExplorer } from "./components/stat_var_explorer";
import { SessionDrawer } from "./components/drawer_session";
import { BrandingProvider } from "./hooks/branding_context";
import {
  ChatSessionProvider,
  useChatSession,
} from "./hooks/chat_session_context";
import { useHashRoute } from "./hooks/use_hash_route";

/** Picks the main view for the current hash route; unknown routes fall back to the Data Agent. */
function renderContent(route: string) {
  switch (route) {
    case "metrics":
      return <MetricsPage />;
    case "download":
      return <DataDownloadTool />;
    case "statvar":
      return <StatVarExplorer />;
    default:
      return <DataAgent />;
  }
}

/** Root component: providers + sidebar/header layout around the routed view. */
export function App() {
  const [route] = useHashRoute();

  return (
    <BrandingProvider>
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
    </BrandingProvider>
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

