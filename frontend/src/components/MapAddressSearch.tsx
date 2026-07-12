import { useEffect, useRef, useState } from "react";
import { GeoJSON, useMap } from "react-leaflet";
import { Search, X } from "lucide-react";
import { fetchGeocodeSuggestions } from "@/api/client";
import type { AoiRing, GeocodeResult } from "@/context/GISContext";
import { geocodeResultToAoiRing } from "@/components/SearchBar";
import { aoiRingToBounds } from "@/components/MapView";
import { Input } from "@/components/ui/input";
import { useLanguage } from "@/context/LanguageContext";

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 3;

/** Address search overlaid on the Landslide page's map - navigation/visual
 * aid only. Selecting a result pans/zooms the map and draws its boundary; it
 * never sets the processing AOI (that's MapBboxDrawTool's job). */
function MapAddressSearch() {
  const { t } = useLanguage();
  const map = useMap();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<GeocodeResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [boundary, setBoundary] = useState<AoiRing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (query.trim().length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      setIsOpen(false);
      return;
    }

    const requestId = ++requestIdRef.current;
    const timer = setTimeout(async () => {
      try {
        const results = await fetchGeocodeSuggestions(query);
        if (requestId !== requestIdRef.current) return;
        setSuggestions(results);
        setIsOpen(true);
        setError(null);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setSuggestions([]);
        setError(err instanceof Error ? err.message : t("geocodeFailed"));
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [query, t]);

  const handleSelect = (suggestion: GeocodeResult) => {
    const ring = geocodeResultToAoiRing(suggestion);
    map.fitBounds(aoiRingToBounds(ring));
    setBoundary(ring);
    setQuery(suggestion.displayName);
    setSuggestions([]);
    setIsOpen(false);
  };

  const handleClear = () => {
    setQuery("");
    setSuggestions([]);
    setIsOpen(false);
    setBoundary(null);
  };

  return (
    <>
      <div className="absolute right-2 top-2 z-[1000] w-64">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder={t("searchAddressPlaceholder")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-8 bg-background pl-8 pr-8 shadow-md"
          />
          {query.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        {isOpen && suggestions.length > 0 && (
          <ul className="mt-1 max-h-48 overflow-auto rounded-md border bg-popover py-1 text-popover-foreground shadow-md">
            {suggestions.map((suggestion, index) => (
              <li key={`${suggestion.lat}-${suggestion.lng}-${index}`}>
                <button
                  type="button"
                  onClick={() => handleSelect(suggestion)}
                  className="block w-full px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                >
                  {suggestion.displayName}
                </button>
              </li>
            ))}
          </ul>
        )}
        {error && (
          <p className="mt-1 rounded bg-background/90 px-1.5 py-0.5 text-xs text-destructive shadow">
            {error}
          </p>
        )}
      </div>
      {boundary && (
        <GeoJSON
          key={boundary.map(([lon, lat]) => `${lon},${lat}`).join(";")}
          data={
            {
              type: "Feature",
              properties: {},
              geometry: { type: "Polygon", coordinates: [[...boundary, boundary[0]]] },
            } as any
          }
          style={{ color: "#dc2626", weight: 2, dashArray: "6 4", fillOpacity: 0.03 }}
        />
      )}
    </>
  );
}

export default MapAddressSearch;
