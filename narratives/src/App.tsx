import Sidebar from "./components/Sidebar";
import Header from "./components/Header";
import DataAgent from "./components/DataAgent";
import MetricsPage from "./components/MetricsPage";
import DataDownloadTool from "./components/DataDownloadTool";
import StatVarExplorer from "./components/StatVarExplorer";
import SessionDrawer from "./components/SessionDrawer";
import { BrandingProvider } from "./hooks/BrandingContext";
import { ChatSessionProvider } from "./hooks/ChatSessionContext";
import { useHashRoute } from "./hooks/useHashRoute";

export default function App() {
  const [route] = useHashRoute();

  return (
    <BrandingProvider>
      <ChatSessionProvider>
        <div className="flex h-screen w-full bg-white overflow-hidden relative">
          <Sidebar />
          <SessionDrawer />
          <main className="flex-1 flex flex-col h-full relative">
            <Header />
            {route === "metrics" ? (
              <MetricsPage />
            ) : route === "download" ? (
              <DataDownloadTool />
            ) : route === "statvar" ? (
              <StatVarExplorer />
            ) : (
              <DataAgent />
            )}
          </main>
        </div>
      </ChatSessionProvider>
    </BrandingProvider>
  );
}

