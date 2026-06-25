/**
 * @fileoverview Main single-page application core setup, integrating layout
 * grids, contexts, and tab route selection.
 */

import React from "react";
import { Sidebar } from "./components/sidebar";
import { Header } from "./components/header";
import { DataAgent } from "./components/data_agent";
import { MetricsPage } from "./components/metrics_page";
import { DataDownloadTool } from "./components/data_download_tool";
import { StatVarExplorer } from "./components/stat_var_explorer";
import { DrawerSession } from "./components/drawer_session";
import { BrandingProvider } from "./hooks/branding_context";
import { ChatSessionProvider } from "./hooks/chat_session_context";
import { useHashRoute } from "./hooks/use_hash_route";

/**
 * Main application component. Sets up routing, branding, and chat session contexts.
 */
export function App() {
  const [route] = useHashRoute();

  /**
   * Helper function to resolve the active page view based on the current hash route.
   */
  const renderContent = () => {
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
  };

  return (
    <BrandingProvider>
      <ChatSessionProvider>
        <div className="flex h-screen w-full bg-white overflow-hidden relative">
          <Sidebar />
          <DrawerSession />
          <main className="flex-1 flex flex-col h-full relative">
            <Header />
            {renderContent()}
          </main>
        </div>
      </ChatSessionProvider>
    </BrandingProvider>
  );
}
