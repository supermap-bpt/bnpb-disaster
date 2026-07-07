import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEffect, type ReactNode } from "react";
import { GISProvider, useGIS } from "../context/GISContext";

const geoJsonClickHandlers: Record<string, () => void> = {};
const geoJsonHoverHandlers: Record<string, { mouseover?: () => void; mouseout?: () => void }> = {};
const geoJsonStyleLog: Record<string, any> = {};
const fitBoundsMock = vi.fn();

// Real react-leaflet's useMap() returns the SAME Leaflet Map instance across
// renders. A mock that returns a fresh object literal every call breaks any
// effect with `map` in its deps array - the identity change re-triggers the
// effect every render, which (since the effect itself causes a re-render via
// context setters) is an infinite loop that hangs the test runner. Must be a
// stable singleton.
const mapInstanceMock = { fitBounds: fitBoundsMock, attributionControl: { setPrefix: vi.fn() } };

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="map-container">{children}</div>
  ),
  TileLayer: () => <div data-testid="tile-layer" />,
  GeoJSON: ({ data, eventHandlers, style }: any) => {
    const id = data.properties.id;
    if (eventHandlers?.click) geoJsonClickHandlers[id] = eventHandlers.click;
    if (id && (eventHandlers?.mouseover || eventHandlers?.mouseout)) {
      geoJsonHoverHandlers[id] = {
        mouseover: eventHandlers.mouseover,
        mouseout: eventHandlers.mouseout,
      };
    }
    if (id) geoJsonStyleLog[id] = style;
    const testId = id ? `geojson-${id}` : "aoi-layer";
    return <div data-testid={testId} />;
  },
  ImageOverlay: ({ url }: { url: string }) => <img data-testid="preview-overlay" src={url} />,
  ZoomControl: () => <div data-testid="zoom-control" />,
  useMap: () => mapInstanceMock,
}));

vi.mock("../api/client", () => ({
  fetchPreview: vi.fn(),
}));

import { fetchPreview } from "../api/client";
import MapView, { aoiRingToBounds } from "./MapView";

beforeEach(() => {
  vi.mocked(fetchPreview).mockReset();
  // Default so tests that select a product but don't care about preview
  // content don't crash on an unresolved mock - dedicated preview tests
  // override this with their own mockResolvedValue.
  vi.mocked(fetchPreview).mockResolvedValue({
    productId: "p1",
    tileUrl: "https://wms.test/process?access_token=default",
    bounds: [[4, 95], [6, 98]],
  });
});

describe("aoiRingToBounds", () => {
  it("computes [[south,west],[north,east]] from a ring of [lon,lat] points", () => {
    expect(
      aoiRingToBounds([
        [95.0, 4.0],
        [98.0, 4.0],
        [98.0, 6.0],
        [95.0, 6.0],
      ])
    ).toEqual([
      [4.0, 95.0],
      [6.0, 98.0],
    ]);
  });
});

const SAMPLE_ITEM = {
  id: "p1",
  name: "p1.SAFE",
  productType: "SENTINEL_1_GRD" as const,
  sensingTime: "2026-01-26T11:43:01Z",
  size: "1632MB",
  polarisation: "VV&VH",
  footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6], [95, 6]]] },
};

function ResultsSeeder({ children }: { children: ReactNode }) {
  const gis = useGIS();
  useEffect(() => {
    gis.setSearchResults([SAMPLE_ITEM], 1);
  }, []);
  return <>{children}</>;
}

describe("MapView", () => {
  it("draws no AOI outline until a place has been searched", () => {
    render(
      <GISProvider>
        <MapView />
      </GISProvider>
    );

    expect(screen.queryByTestId("aoi-layer")).not.toBeInTheDocument();
  });

  it("draws the AOI outline once placeRing is set, and fits the map to it", () => {
    function PlaceSeeder({ children }: { children: ReactNode }) {
      const gis = useGIS();
      useEffect(() => {
        gis.setPlaceRing([
          [95.0, 4.0],
          [98.0, 4.0],
          [98.0, 6.0],
          [95.0, 6.0],
        ]);
      }, []);
      return <>{children}</>;
    }

    fitBoundsMock.mockClear();
    render(
      <GISProvider>
        <PlaceSeeder>
          <MapView />
        </PlaceSeeder>
      </GISProvider>
    );

    expect(screen.getByTestId("aoi-layer")).toBeInTheDocument();
    expect(fitBoundsMock).toHaveBeenCalledWith([
      [4.0, 95.0],
      [6.0, 98.0],
    ]);
  });

  it("renders a GeoJSON layer per search result, styled differently when selected", () => {
    render(
      <GISProvider>
        <ResultsSeeder>
          <MapView />
        </ResultsSeeder>
      </GISProvider>
    );

    expect(screen.getByTestId("geojson-p1")).toBeInTheDocument();
    expect(geoJsonStyleLog["p1"]).toEqual({ color: "#3b82f6", weight: 1, fillOpacity: 0.08 });

    act(() => geoJsonClickHandlers["p1"]());

    expect(geoJsonStyleLog["p1"]).toEqual({ color: "#2563eb", weight: 3, fillOpacity: 0.25 });
  });

  it("hovering a card (context hoveredProductId) restyles the matching footprint", () => {
    function HoverSetter({ children }: { children: ReactNode }) {
      const gis = useGIS();
      return (
        <>
          <button onClick={() => gis.setHoveredProductId("p1")}>hover-p1</button>
          {children}
        </>
      );
    }

    render(
      <GISProvider>
        <ResultsSeeder>
          <HoverSetter>
            <MapView />
          </HoverSetter>
        </ResultsSeeder>
      </GISProvider>
    );

    expect(geoJsonStyleLog["p1"]).toEqual({ color: "#3b82f6", weight: 1, fillOpacity: 0.08 });

    act(() => screen.getByText("hover-p1").click());

    expect(geoJsonStyleLog["p1"]).toEqual({ color: "#1d4ed8", weight: 2, fillOpacity: 0.18 });
  });

  it("hovering a footprint on the map sets hoveredProductId in context, mouseout clears it", () => {
    function HoverProbe() {
      const gis = useGIS();
      return <span data-testid="hovered">{gis.hoveredProductId ?? "none"}</span>;
    }

    render(
      <GISProvider>
        <ResultsSeeder>
          <MapView />
          <HoverProbe />
        </ResultsSeeder>
      </GISProvider>
    );

    act(() => geoJsonHoverHandlers["p1"].mouseover?.());
    expect(screen.getByTestId("hovered").textContent).toBe("p1");

    act(() => geoJsonHoverHandlers["p1"].mouseout?.());
    expect(screen.getByTestId("hovered").textContent).toBe("none");
  });

  it("selecting a product zooms to its footprint and loads its preview (same product id throughout)", async () => {
    fitBoundsMock.mockClear();
    vi.mocked(fetchPreview).mockReset();
    vi.mocked(fetchPreview).mockResolvedValue({
      productId: "p1",
      tileUrl: "https://wms.test/process?access_token=tok",
      bounds: [[4, 95], [6, 98]],
    });

    render(
      <GISProvider>
        <ResultsSeeder>
          <MapView />
        </ResultsSeeder>
      </GISProvider>
    );

    act(() => geoJsonClickHandlers["p1"]());

    expect(fitBoundsMock).toHaveBeenCalledWith([
      [4, 95],
      [6, 98],
    ]);
    expect(fetchPreview).toHaveBeenCalledWith("p1");
    expect(await screen.findByTestId("preview-overlay")).toHaveAttribute(
      "src",
      "https://wms.test/process?access_token=tok"
    );
  });
});
