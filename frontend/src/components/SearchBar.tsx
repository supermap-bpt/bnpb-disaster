import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Search, X } from "lucide-react";
import { useGIS, type AoiRing, type GeocodeResult } from "../context/GISContext";
import { fetchGeocodeSuggestions } from "../api/client";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/context/LanguageContext";

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 3;

export function geocodeResultToAoiRing(suggestion: GeocodeResult): AoiRing {
  if (suggestion.polygon) {
    return suggestion.polygon.map(([lon, lat]) => [lon, lat]);
  }
  const [minLon, minLat, maxLon, maxLat] = suggestion.bbox;
  return [
    [minLon, minLat],
    [maxLon, minLat],
    [maxLon, maxLat],
    [minLon, maxLat],
  ];
}

function SearchBar({ className }: { className?: string }) {
  const { setGeocodeResult, setPlaceRing, setAddressQuery, error, setError, resetCount } = useGIS();
  const { t } = useLanguage();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<GeocodeResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (resetCount === 0) return;
    setQuery("");
    setSuggestions([]);
    setIsOpen(false);
  }, [resetCount]);

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
  }, [query, setError]);

  const handleSelect = (suggestion: GeocodeResult) => {
    setGeocodeResult(suggestion);
    setPlaceRing(geocodeResultToAoiRing(suggestion));
    setQuery(suggestion.displayName);
    setAddressQuery(suggestion.displayName);
    setSuggestions([]);
    setIsOpen(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && suggestions.length > 0) {
      event.preventDefault();
      handleSelect(suggestions[0]);
    }
  };

  const handleClear = () => {
    setQuery("");
    setSuggestions([]);
    setIsOpen(false);
    setGeocodeResult(null);
    setPlaceRing(null);
    setAddressQuery("");
  };

  return (
    <div role="search" className={cn("relative flex w-full flex-col gap-1", className)}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          placeholder={t("searchAddressPlaceholder")}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setAddressQuery(event.target.value);
          }}
          onKeyDown={handleKeyDown}
          className="pl-8 pr-8"
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
        <ul className="absolute top-full z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover py-1 text-popover-foreground shadow-md">
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
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export default SearchBar;
