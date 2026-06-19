import React from "react";
import { Sidebar } from "./components/Sidebar";
import { Header } from "./components/Header";
import { DataAgent } from "./components/DataAgent";
import { MetricsPage } from "./components/MetricsPage";
import { DataDownloadTool } from "./components/DataDownloadTool";
import { StatVarExplorer } from "./components/StatVarExplorer";
import { SessionDrawer } from "./components/SessionDrawer";
import { BrandingProvider } from "./hooks/BrandingContext";
import { ChatSessionProvider } from "./hooks/ChatSessionContext";
import { useHashRoute } from "./hooks/useHashRoute";

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
          <SessionDrawer />
          <main className="flex-1 flex flex-col h-full relative">
            <Header />
            {renderContent()}
          </main>
        </div>
      </ChatSessionProvider>
    </BrandingProvider>
  );
}
