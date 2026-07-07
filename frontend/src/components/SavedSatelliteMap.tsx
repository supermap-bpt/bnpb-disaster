import { useEffect } from "react";
import { GeoJSON, ImageOverlay, MapContainer, TileLayer, ZoomControl, useMap } from "react-leaflet";
import { getSavedSatelliteThumbnailUrl, type SavedSatelliteDetail } from "../api/client";
import { footprintBounds } from "@/components/product-info/FootprintPreview";

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

function SavedSatelliteMap({ selected }: { selected: SavedSatelliteDetail | null }) {
  return (
    <MapContainer center={[-2.5, 118]} zoom={5} zoomControl={false} className="h-full w-full">
      <RemoveLeafletPrefix />
      <TileLayer
        url="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
        attribution='<a href="https://browser.dataspace.copernicus.eu/">Satellite by Copernicus</a>'
      />
      <ZoomControl position="bottomright" />
      <SelectedFootprintSync selected={selected} />
    </MapContainer>
  );
}

export default SavedSatelliteMap;
