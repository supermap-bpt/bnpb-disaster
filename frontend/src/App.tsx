import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { GISProvider } from "./context/GISContext";
import { LanguageProvider } from "./context/LanguageContext";
import { ActivityNotificationsProvider } from "./context/ActivityNotificationsContext";
import Header from "./components/Header";
import DashboardPage from "./pages/DashboardPage";
import FindSatellitePage from "./pages/FindSatellitePage";
import SavedSatellitePage from "./pages/SavedSatellitePage";
import FloodPage from "./pages/FloodPage";
import LogsPage from "./pages/LogsPage";
import PlaceholderPage from "./pages/PlaceholderPage";

function AppShell() {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <Header />
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/satellite-explorer" element={<FindSatellitePage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/pre-disaster/landslide" element={<SavedSatellitePage />} />
        <Route path="/pre-disaster/flood" element={<FloodPage />} />
        <Route path="/during-disaster" element={<PlaceholderPage titleKey="navDuringDisaster" />} />
        <Route path="/prediction-disaster" element={<PlaceholderPage titleKey="navPredictionDisaster" />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <LanguageProvider>
      <GISProvider>
        <ActivityNotificationsProvider>
          <BrowserRouter>
            <AppShell />
          </BrowserRouter>
          <Toaster richColors position="top-right" />
        </ActivityNotificationsProvider>
      </GISProvider>
    </LanguageProvider>
  );
}

export default App;
