import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import MapView from "@/components/MapView";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/context/LanguageContext";

function FindSatellitePage() {
  const [resultsOpen, setResultsOpen] = useState(false);
  const { t } = useLanguage();

  return (
    <main className="relative flex-1 overflow-hidden">
      <MapView />
      <Button
        type="button"
        onClick={() => setResultsOpen(true)}
        className="absolute left-3 top-3 z-[1000] shadow-md md:hidden"
      >
        {t("filterAndResults")}
      </Button>

      <div
        className={`absolute inset-y-3 left-3 z-[1400] flex w-[380px] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border bg-background/85 shadow-lg backdrop-blur transition-transform duration-200 md:translate-x-0 ${resultsOpen ? "translate-x-0" : "-translate-x-[120%]"
          }`}
      >
        <div className="flex items-center justify-between border-b px-3 py-2 md:hidden">
          <span className="text-sm font-semibold">{t("filterAndResults")}</span>
          <button
            type="button"
            onClick={() => setResultsOpen(false)}
            aria-label={t("closePanel")}
            className="text-muted-foreground"
          >
            &times;
          </button>
        </div>
        <Sidebar />
      </div>
    </main>
  );
}

export default FindSatellitePage;
