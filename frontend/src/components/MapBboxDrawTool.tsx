import { useCallback, useRef, useState } from "react";
import { Marker, Rectangle, useMap, useMapEvents } from "react-leaflet";
import L, { type LatLng, type LatLngBoundsExpression, type LeafletEvent } from "leaflet";
import { BoxSelect, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/context/LanguageContext";

/** [minLon, minLat, maxLon, maxLat] - the exact shape processLandslide's
 * `aoi` param and the backend's SNAP Subset crop both expect. */
export type Bbox = [number, number, number, number];

const HANDLE_ICON = L.divIcon({
  className: "",
  html: '<div style="width:10px;height:10px;background:#2563eb;border:2px solid white;border-radius:2px;"></div>',
  iconSize: [10, 10],
  iconAnchor: [5, 5],
});

function boundsToBbox(a: LatLng, b: LatLng): Bbox {
  return [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)];
}

function bboxCorners(bbox: Bbox) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  return {
    nw: [maxLat, minLon] as [number, number],
    ne: [maxLat, maxLon] as [number, number],
    sw: [minLat, minLon] as [number, number],
    se: [minLat, maxLon] as [number, number],
  };
}

/** Click-drag-to-draw, then drag-corner-to-resize bounding-box tool for the
 * Landslide page's map. This IS the processing AOI (unlike
 * MapAddressSearch's purely-visual boundary). No leaflet-draw dependency -
 * built from react-leaflet's own Rectangle/Marker/useMapEvents. */
function MapBboxDrawTool({
  bbox,
  onBboxChange,
}: {
  bbox: Bbox | null;
  onBboxChange: (bbox: Bbox | null) => void;
}) {
  const { t } = useLanguage();
  const map = useMap();
  const [isDrawing, setIsDrawing] = useState(false);
  const [draftBounds, setDraftBounds] = useState<[LatLng, LatLng] | null>(null);
  const startRef = useRef<LatLng | null>(null);

  useMapEvents({
    mousedown(event) {
      if (!isDrawing) return;
      startRef.current = event.latlng;
      setDraftBounds([event.latlng, event.latlng]);
      map.dragging.disable();
    },
    mousemove(event) {
      if (!isDrawing || !startRef.current) return;
      setDraftBounds([startRef.current as LatLng, event.latlng]);
    },
    mouseup(event) {
      if (!isDrawing || !startRef.current) return;
      const start = startRef.current;
      const end = event.latlng;
      startRef.current = null;
      setDraftBounds(null);
      setIsDrawing(false);
      map.dragging.enable();
      if (start.lat === end.lat && start.lng === end.lng) return; // zero-area click, discard
      onBboxChange(boundsToBbox(start, end));
    },
  });

  const startDrawing = () => {
    setIsDrawing(true);
    onBboxChange(null);
  };

  const handleCornerDrag = useCallback(
    (corner: "nw" | "ne" | "sw" | "se") => (event: LeafletEvent) => {
      if (!bbox) return;
      const marker = event.target as L.Marker;
      const { lat, lng } = marker.getLatLng();
      const [minLon, minLat, maxLon, maxLat] = bbox;
      let next: Bbox;
      if (corner === "nw") next = [lng, minLat, maxLon, lat];
      else if (corner === "ne") next = [minLon, minLat, lng, lat];
      else if (corner === "sw") next = [lng, lat, maxLon, maxLat];
      else next = [minLon, lat, lng, maxLat];
      const [nMinLon, nMinLat, nMaxLon, nMaxLat] = next;
      if (nMinLon >= nMaxLon || nMinLat >= nMaxLat) return; // clamp: never invert
      onBboxChange(next);
    },
    [bbox, onBboxChange]
  );

  const corners = bbox ? bboxCorners(bbox) : null;

  return (
    <>
      <div className="absolute right-2 top-16 z-[1000] flex flex-col items-end gap-1">
        <Button
          type="button"
          size="icon"
          variant={isDrawing ? "default" : "outline"}
          aria-label={t("landslideDrawBbox")}
          data-testid="bbox-draw-button"
          onClick={startDrawing}
          className="h-8 w-8 shadow-md"
        >
          <BoxSelect className="h-4 w-4" />
        </Button>
        {bbox && (
          <div className="flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-[10px] shadow-md">
            <span>
              {bbox[0].toFixed(2)}, {bbox[1].toFixed(2)} → {bbox[2].toFixed(2)}, {bbox[3].toFixed(2)}
            </span>
            <button
              type="button"
              aria-label={t("landslideClearBbox")}
              data-testid="bbox-clear-button"
              onClick={() => onBboxChange(null)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>
      {draftBounds && (
        <Rectangle
          // react-leaflet's LatLngBoundsExpression type wants tuples or a
          // LatLngBounds instance, but Leaflet's runtime (L.latLngBounds)
          // happily accepts LatLng instances too - this cast is type-only.
          bounds={draftBounds as unknown as LatLngBoundsExpression}
          pathOptions={{ color: "#2563eb", weight: 2, dashArray: "4 4" }}
        />
      )}
      {!draftBounds && bbox && (
        <Rectangle
          bounds={[
            [bbox[1], bbox[0]],
            [bbox[3], bbox[2]],
          ]}
          pathOptions={{ color: "#2563eb", weight: 2 }}
        />
      )}
      {corners && (
        <>
          <Marker position={corners.nw} icon={HANDLE_ICON} draggable eventHandlers={{ drag: handleCornerDrag("nw") }} />
          <Marker position={corners.ne} icon={HANDLE_ICON} draggable eventHandlers={{ drag: handleCornerDrag("ne") }} />
          <Marker position={corners.sw} icon={HANDLE_ICON} draggable eventHandlers={{ drag: handleCornerDrag("sw") }} />
          <Marker position={corners.se} icon={HANDLE_ICON} draggable eventHandlers={{ drag: handleCornerDrag("se") }} />
        </>
      )}
    </>
  );
}

export default MapBboxDrawTool;
