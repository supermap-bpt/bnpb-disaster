import { useEffect, useRef } from "react";
import type { LatLngBoundsExpression } from "leaflet";
import {
  GeoJSON,
  ImageOverlay,
  MapContainer,
  TileLayer,
  ZoomControl,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { useGIS, type AoiRing, type SearchResultItem } from "../context/GISContext";
import { fetchPreview, fetchSearch } from "../api/client";
import { flattenFootprintPoints } from "@/lib/geometry";
import { getDemnasFilename, getDemnasLoginDownloadUrl, getDemnasPreviewImageUrl, hasPreview } from "@/lib/satellite";

const WST_VIEWPORT_RESEARCH_DEBOUNCE_MS = 500;

export function aoiRingToBounds(ring: AoiRing): LatLngBoundsExpression {
  const lons = ring.map(([lon]) => lon);
  const lats = ring.map(([, lat]) => lat);
  return [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
}

function footprintBounds(item: SearchResultItem): LatLngBoundsExpression {
  const points = flattenFootprintPoints(item.footprint.coordinates);
  const lons = points.map(([lon]) => lon);
  const lats = points.map(([, lat]) => lat);
  return [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
}

/** Navigates the map to (and centers the search AOI on) a geocoded place -
 * the only search mode now: AOI always comes from a searched location. */
function FitBoundsToPlace() {
  const { placeRing } = useGIS();
  const map = useMap();
  useEffect(() => {
    if (placeRing && placeRing.length > 0) {
      map.fitBounds(aoiRingToBounds(placeRing));
    }
  }, [placeRing, map]);
  return null;
}

function AoiLayer() {
  const { placeRing } = useGIS();
  if (placeRing === null) return null;
  return (
    <GeoJSON
      data={
        {
          type: "Feature",
          properties: {},
          geometry: { type: "Polygon", coordinates: [[...placeRing, placeRing[0]]] },
        } as any
      }
      style={{ color: "#dc2626", weight: 2, dashArray: "6 4", fillOpacity: 0.03 }}
    />
  );
}

export function footprintStyle(isSelected: boolean, isHovered: boolean) {
  if (isSelected) return { color: "#2563eb", weight: 3, fillOpacity: 0.25 };
  if (isHovered) return { color: "#1d4ed8", weight: 2, fillOpacity: 0.18 };
  return { color: "#3b82f6", weight: 1, fillOpacity: 0.08 };
}

/** DEMNAS's full matching-tile coverage grid (can be thousands of tiles),
 * drawn as one merged layer - unlike FootprintLayers below, which renders one
 * clickable/selectable GeoJSON per currently-loaded Sidebar card. Only the
 * current page's cards are tied into selection/preview state, since only
 * they have full backend-cached data for View on Map/Info/Save; clicking a
 * coverage-grid tile instead pops up its BIG-hosted preview image, filename,
 * and login download link - self-contained from the tile's id alone. */
const DEMNAS_TILE_STYLE = { color: "#60a5fa", weight: 1, fillOpacity: 0.02 };
const DEMNAS_TILE_HOVER_STYLE = { color: "#3b82f6", weight: 2, fillOpacity: 0.12 };

/** Plain HTML (not JSX) because Leaflet popups render outside React's tree -
 * bindPopup takes a DOM node or HTML string, not a component. `id` is safe to
 * interpolate raw: it's BIG's own DEMNAS tile catalog grid code (backend
 * data, never end-user input), not a value that needs escaping. */
function buildDemnasPopupHtml(id: string): string {
  const previewUrl = getDemnasPreviewImageUrl(id);
  const filename = getDemnasFilename(id);
  const downloadUrl = getDemnasLoginDownloadUrl(id);
  return `
    <div style="display:flex;flex-direction:column;gap:6px;min-width:160px;">
      <img src="${previewUrl}" alt="${filename}" onerror="this.style.display='none'" style="width:100%;border-radius:4px;" />
      <span style="font-size:11px;word-break:break-all;">${filename}</span>
      <a href="${downloadUrl}" target="_blank" rel="noopener noreferrer"
         style="display:inline-block;text-align:center;background:#3b82f6;color:#fff;font-size:11px;padding:4px 8px;border-radius:4px;text-decoration:none;">
        Download
      </a>
    </div>
  `;
}

function DemnasCoverageLayer() {
  const { demnasFootprints } = useGIS();

  if (demnasFootprints.length === 0) return null;

  const featureCollection = {
    type: "FeatureCollection",
    features: demnasFootprints.map((item) => ({
      type: "Feature",
      properties: { id: item.id },
      geometry: item.footprint,
    })),
  };

  return (
    <GeoJSON
      key={`${demnasFootprints.length}-${demnasFootprints[0]?.id}-${demnasFootprints[demnasFootprints.length - 1]?.id}`}
      data={featureCollection as any}
      interactive={true}
      style={DEMNAS_TILE_STYLE}
      onEachFeature={(feature: any, layer: any) => {
        layer.bindPopup(buildDemnasPopupHtml(feature.properties.id));
        layer.on("mouseover", () => layer.setStyle(DEMNAS_TILE_HOVER_STYLE));
        layer.on("mouseout", () => layer.setStyle(DEMNAS_TILE_STYLE));
      }}
    />
  );
}

function FootprintLayers() {
  const { searchResults, selectedProductId, hoveredProductId, selectProduct, setHoveredProductId } =
    useGIS();

  return (
    <>
      {searchResults.map((item) => (
        <GeoJSON
          key={item.id}
          data={{ type: "Feature", properties: { id: item.id }, geometry: item.footprint } as any}
          eventHandlers={{
            click: () => selectProduct(item.id),
            mouseover: () => setHoveredProductId(item.id),
            mouseout: () => setHoveredProductId(null),
          }}
          style={footprintStyle(item.id === selectedProductId, item.id === hoveredProductId)}
        />
      ))}
    </>
  );
}

/** Selecting a product (from a card or a footprint click) zooms to its
 * footprint and loads its preview - search -> selection -> preview always
 * refer to the same product id. */
function SelectedProductSync() {
  const { selectedProductId, searchResults, setPreviewData, setIsPreviewLoading, setError } =
    useGIS();
  const map = useMap();

  useEffect(() => {
    if (selectedProductId === null) return;
    const item = searchResults.find((result) => result.id === selectedProductId);
    if (!item) return;

    map.fitBounds(footprintBounds(item));

    if (!hasPreview(item.productType)) {
      setPreviewData(null);
      return;
    }

    let cancelled = false;
    setIsPreviewLoading(true);
    setError(null);
    fetchPreview(item.id)
      .then((preview) => {
        if (!cancelled) setPreviewData(preview);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Gagal memuat citra.");
      })
      .finally(() => {
        if (!cancelled) setIsPreviewLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedProductId]);

  return null;
}

function PreviewLayer() {
  const { previewData } = useGIS();
  if (previewData === null) return null;
  const bounds: LatLngBoundsExpression = previewData.bounds;
  return <ImageOverlay url={previewData.tileUrl} bounds={bounds} />;
}

function RemoveLeafletPrefix() {
  const map = useMap();

  useEffect(() => {
    map.attributionControl.setPrefix("");
  }, [map]);

  return null;
}

/** Sentinel-3 SLSTR L2 WST swaths are near-global, so (unlike every other
 * product type, which searches a geocoded place's AOI) browsing WST results
 * works by panning the map itself - each pan re-searches the current
 * viewport, debounced, matching Copernicus Browser's behavior. Scoped to WST
 * only per product decision; other product types keep the address-search flow. */
function WstViewportResearch() {
  const { lastSearchFilter, setSearchResults, setIsSearching, setError } = useGIS();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const map = useMapEvents({
    moveend: () => {
      if (!lastSearchFilter?.productType.includes("SENTINEL_3_SLSTR_L2_WST")) return;

      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const bounds = map.getBounds();
        const ring: AoiRing = [
          [bounds.getWest(), bounds.getSouth()],
          [bounds.getEast(), bounds.getSouth()],
          [bounds.getEast(), bounds.getNorth()],
          [bounds.getWest(), bounds.getNorth()],
        ];
        setIsSearching(true);
        setError(null);
        fetchSearch(lastSearchFilter, ring, 0)
          .then(({ results, total }) => setSearchResults(results, total))
          .catch((err) => setError(err instanceof Error ? err.message : "Gagal memuat ulang area peta."))
          .finally(() => setIsSearching(false));
      }, WST_VIEWPORT_RESEARCH_DEBOUNCE_MS);
    },
  });

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return null;
}

function MapView() {
  return (
    <MapContainer
      center={[-2.5, 118]}
      zoom={5}
      minZoom={2}
      zoomControl={false}
      className="h-full w-full"
    >
      <RemoveLeafletPrefix />
      <TileLayer
        url="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
        attribution='<a href="https://browser.dataspace.copernicus.eu/">Satellite by Copernicus</a>'
      />
      <ZoomControl position="bottomright" />
      <FitBoundsToPlace />
      <AoiLayer />
      <DemnasCoverageLayer />
      <FootprintLayers />
      <SelectedProductSync />
      <PreviewLayer />
      <WstViewportResearch />
    </MapContainer>
  );
}

export default MapView;
