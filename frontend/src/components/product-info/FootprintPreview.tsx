import type { LatLngBoundsExpression } from "leaflet";
import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import type { Footprint } from "@/context/GISContext";

export function footprintBounds(footprint: Footprint): LatLngBoundsExpression {
  const points = footprint.coordinates.flat();
  const lons = points.map(([lon]) => lon);
  const lats = points.map(([, lat]) => lat);
  return [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
}

function FootprintPreview({ footprint }: { footprint: Footprint }) {
  if (footprint.coordinates.length === 0 || footprint.coordinates[0].length === 0) {
    return null;
  }
  return (
    <MapContainer
      bounds={footprintBounds(footprint)}
      className="h-64 w-full rounded-lg border"
      dragging={false}
      zoomControl={false}
      scrollWheelZoom={false}
      doubleClickZoom={false}
      touchZoom={false}
      boxZoom={false}
      keyboard={false}
      attributionControl={false}
    >
      <TileLayer url="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}" />
      <GeoJSON
        data={{ type: "Feature", properties: {}, geometry: footprint } as any}
        style={{ color: "#3b82f6", weight: 2, fillOpacity: 0.15 }}
      />
    </MapContainer>
  );
}

export default FootprintPreview;
