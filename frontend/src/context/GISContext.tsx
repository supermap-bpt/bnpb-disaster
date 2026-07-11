import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { FilterFormValues, ProductType } from "../schemas/filterSchema";

export interface GeocodeResult {
  lat: number;
  lng: number;
  displayName: string;
  bbox: [number, number, number, number];
  polygon: number[][] | null;
}

export interface Footprint {
  type: string;
  // Polygon: [ring]. MultiPolygon: [[ring], [ring], ...] - CDSE returns
  // MultiPolygon for footprints crossing the antimeridian (e.g. Sentinel-3
  // WST's near-global, near-polar swaths).
  coordinates: number[][][] | number[][][][];
}

export interface SearchResultItem {
  id: string;
  name: string;
  productType: ProductType;
  sensingTime: string;
  size: string;
  polarisation: string;
  cloudCoverPercentage?: number | null;
  footprint: Footprint;
}

export interface PreviewData {
  productId: string;
  tileUrl: string;
  bounds: [[number, number], [number, number]];
}

/** [lon, lat] ring for the geocoded place's AOI (administrative boundary
 * polygon if Nominatim has one, else its bounding-box rectangle). */
export type AoiRing = [number, number][];

/** Whole-Indonesia bounding box, used as the AOI when the address search
 * box is empty. Centroid (118, -2.5) matches MapView's default map center. */
export const INDONESIA_BBOX: AoiRing = [
  [95.0, -11.0],
  [141.0, -11.0],
  [141.0, 6.0],
  [95.0, 6.0],
];

interface GISContextValue {
  geocodeResult: GeocodeResult | null;
  searchResults: SearchResultItem[];
  searchTotal: number;
  selectedProductId: string | null;
  hoveredProductId: string | null;
  previewData: PreviewData | null;
  placeRing: AoiRing | null;
  addressQuery: string;
  lastSearchFilter: FilterFormValues | null;
  isSearching: boolean;
  isPreviewLoading: boolean;
  error: string | null;
  resetCount: number;
  setGeocodeResult: (result: GeocodeResult | null) => void;
  setAddressQuery: (value: string) => void;
  setSearchResults: (results: SearchResultItem[], total: number) => void;
  appendSearchResults: (results: SearchResultItem[], total: number) => void;
  selectProduct: (productId: string | null) => void;
  setHoveredProductId: (productId: string | null) => void;
  setPreviewData: (data: PreviewData | null) => void;
  setPlaceRing: (ring: AoiRing | null) => void;
  setLastSearchFilter: (filter: FilterFormValues | null) => void;
  setIsSearching: (value: boolean) => void;
  setIsPreviewLoading: (value: boolean) => void;
  setError: (message: string | null) => void;
  resetAll: () => void;
}

const GISContext = createContext<GISContextValue | null>(null);

export function GISProvider({ children }: { children: ReactNode }) {
  const [geocodeResult, setGeocodeResult] = useState<GeocodeResult | null>(null);
  const [searchResults, setSearchResultsState] = useState<SearchResultItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [hoveredProductId, setHoveredProductId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [placeRing, setPlaceRing] = useState<AoiRing | null>(null);
  const [addressQuery, setAddressQuery] = useState("");
  const [lastSearchFilter, setLastSearchFilter] = useState<FilterFormValues | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetCount, setResetCount] = useState(0);

  const setSearchResults = (results: SearchResultItem[], total: number) => {
    setSearchResultsState(results);
    setSearchTotal(total);
  };

  const appendSearchResults = (results: SearchResultItem[], total: number) => {
    setSearchResultsState((prev) => [...prev, ...results]);
    setSearchTotal(total);
  };

  const selectProduct = (productId: string | null) => {
    setSelectedProductId(productId);
    if (productId === null) {
      setPreviewData(null);
    }
  };

  const resetAll = () => {
    setGeocodeResult(null);
    setPlaceRing(null);
    setAddressQuery("");
    setSearchResultsState([]);
    setSearchTotal(0);
    setSelectedProductId(null);
    setPreviewData(null);
    setLastSearchFilter(null);
    setError(null);
    setResetCount((c) => c + 1);
  };

  const value = useMemo<GISContextValue>(
    () => ({
      geocodeResult,
      searchResults,
      searchTotal,
      selectedProductId,
      hoveredProductId,
      previewData,
      placeRing,
      addressQuery,
      lastSearchFilter,
      isSearching,
      isPreviewLoading,
      error,
      resetCount,
      setGeocodeResult,
      setAddressQuery,
      setSearchResults,
      appendSearchResults,
      selectProduct,
      setHoveredProductId,
      setPreviewData,
      setPlaceRing,
      setLastSearchFilter,
      setIsSearching,
      setIsPreviewLoading,
      setError,
      resetAll,
    }),
    [
      geocodeResult,
      searchResults,
      searchTotal,
      selectedProductId,
      hoveredProductId,
      previewData,
      placeRing,
      addressQuery,
      lastSearchFilter,
      isSearching,
      isPreviewLoading,
      error,
      resetCount,
    ]
  );

  return <GISContext.Provider value={value}>{children}</GISContext.Provider>;
}

export function useGIS(): GISContextValue {
  const ctx = useContext(GISContext);
  if (ctx === null) {
    throw new Error("useGIS must be used within a GISProvider");
  }
  return ctx;
}
