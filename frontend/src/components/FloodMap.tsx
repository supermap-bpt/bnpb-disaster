import { useEffect } from "react";
import { GeoJSON, ImageOverlay, MapContainer, TileLayer, ZoomControl, useMap } from "react-leaflet";
import { getSavedSatelliteThumbnailUrl, type SavedSatelliteDetail } from "../api/client";
import { footprintBounds } from "@/components/product-info/FootprintPreview";
import MapAddressSearch from "./MapAddressSearch";
import MapBboxDrawTool, { type Bbox } from "./MapBboxDrawTool";

function RemoveLeafletPrefix() {
  const map = useMap();
  useEffect(() => {
    map.attributionControl.setPrefix("");
  }, [map]);
  return null;
}

function SelectedFootprintSync({ selected }: { selected: SavedSatelliteDetail | null }) {
  const map = useMap();

  useEffect(() => {
    if (selected === null) return;
    map.fitBounds(footprintBounds(selected.footprint));
  }, [selected, map]);

  if (selected === null) return null;

  return (
    <>
      {selected.preview && (
        <ImageOverlay
          url={getSavedSatelliteThumbnailUrl(selected.preview)}
          bounds={footprintBounds(selected.footprint)}
        />
      )}
      <GeoJSON
        key={selected.id}
        data={{ type: "Feature", properties: {}, geometry: selected.footprint } as any}
        style={{ color: "#2563eb", weight: 3, fillOpacity: 0.2 }}
      />
    </>
  );
}

export interface FloodOverlay {
  url: string;
  // Leaflet bounds [[south, west], [north, east]]
  bounds: [[number, number], [number, number]];
}

function FloodOverlaySync({ overlay }: { overlay: FloodOverlay | null }) {
  const map = useMap();

  useEffect(() => {
    if (overlay === null) return;
    map.fitBounds(overlay.bounds);
  }, [overlay, map]);

  if (overlay === null) return null;

  return <ImageOverlay url={overlay.url} bounds={overlay.bounds} opacity={1} zIndex={500} />;
}

function FloodMap({
  selected,
  overlay = null,
  bbox = null,
  onBboxChange = () => {},
}: {
  selected: SavedSatelliteDetail | null;
  overlay?: FloodOverlay | null;
  bbox?: Bbox | null;
  onBboxChange?: (bbox: Bbox | null) => void;
}) {
  return (
    <MapContainer center={[-2.5, 118]} zoom={5} zoomControl={false} className="h-full w-full">
      <RemoveLeafletPrefix />
      <TileLayer
        url="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
        attribution='<a href="https://browser.dataspace.copernicus.eu/">Satellite by Copernicus</a>'
      />
      <ZoomControl position="bottomright" />
      <SelectedFootprintSync selected={selected} />
      <FloodOverlaySync overlay={overlay} />
      <MapAddressSearch />
      <MapBboxDrawTool bbox={bbox} onBboxChange={onBboxChange} />
    </MapContainer>
  );
}

export default FloodMap;
export type { Bbox };
