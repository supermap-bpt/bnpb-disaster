import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";
import type { SavedSatelliteDetail } from "../api/client";
import { LanguageProvider } from "../context/LanguageContext";
import FloodMap from "./FloodMap";

function renderMap(ui: ReactElement) {
  return render(<LanguageProvider>{ui}</LanguageProvider>);
}

const fitBoundsMock = vi.fn();

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  GeoJSON: () => <div data-testid="geojson" />,
  ImageOverlay: (props: { url: string }) => <div data-testid="image-overlay" data-url={props.url} />,
  ZoomControl: () => <div data-testid="zoom-control" />,
  useMap: () => ({
    fitBounds: fitBoundsMock,
    attributionControl: { setPrefix: vi.fn() },
    dragging: { enable: vi.fn(), disable: vi.fn() },
  }),
  useMapEvents: () => ({
    fitBounds: fitBoundsMock,
    attributionControl: { setPrefix: vi.fn() },
    dragging: { enable: vi.fn(), disable: vi.fn() },
  }),
  Rectangle: () => <div data-testid="rectangle" />,
  Marker: () => <div data-testid="marker" />,
}));

const SAMPLE_DETAIL: SavedSatelliteDetail = {
  id: "sat-1",
  satelliteName: "Aceh Tamiang Flood 14 Jan",
  mission: "Sentinel-1",
  instrumentName: "SAR",
  polarisation: "VV",
  sensingTime: "2025-01-14T11:43:01Z",
  size: "1632MB",
  preview: null,
  savedAt: "2025-01-14T12:00:00Z",
  fileStatus: "completed",
  productId: "p1",
  directoryPath: "storage/satellites/sat-1",
  summary: [],
  product: [],
  instrument: [],
  platform: [],
  other: [],
  downloadSingleFile: "p1.SAFE",
  footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6], [95, 6]]] },
  createdAt: "2025-01-14T12:00:00Z",
  updatedAt: "2025-01-14T12:00:00Z",
};

describe("FloodMap", () => {
  it("renders a map with no footprint layer when nothing is selected", () => {
    renderMap(<FloodMap selected={null} />);

    expect(screen.getByTestId("map-container")).toBeInTheDocument();
    expect(screen.queryByTestId("geojson")).not.toBeInTheDocument();
  });

  it("renders the footprint and zooms to it once a satellite is selected", () => {
    renderMap(<FloodMap selected={SAMPLE_DETAIL} />);

    expect(screen.getByTestId("geojson")).toBeInTheDocument();
    expect(fitBoundsMock).toHaveBeenCalledWith([
      [4, 95],
      [6, 98],
    ]);
  });

  it("renders the satellite imagery overlay when a preview is available", () => {
    renderMap(
      <FloodMap selected={{ ...SAMPLE_DETAIL, preview: "storage/satellites/sat-1/thumbnail.jpg" }} />
    );

    const overlay = screen.getByTestId("image-overlay");
    expect(overlay).toHaveAttribute(
      "data-url",
      "http://localhost:8000/storage/satellites/sat-1/thumbnail.jpg"
    );
  });

  it("does not render an imagery overlay when there is no preview", () => {
    renderMap(<FloodMap selected={SAMPLE_DETAIL} />);

    expect(screen.queryByTestId("image-overlay")).not.toBeInTheDocument();
  });

  it("renders the address search and bbox draw tool", () => {
    renderMap(<FloodMap selected={null} />);

    expect(screen.getByPlaceholderText(/cari alamat/i)).toBeInTheDocument();
    expect(screen.getByTestId("bbox-draw-button")).toBeInTheDocument();
  });

  it("passes bbox/onBboxChange through to the draw tool", () => {
    const onBboxChange = vi.fn();
    renderMap(
      <FloodMap selected={null} bbox={[97.5, 4.0, 98.3, 5.0]} onBboxChange={onBboxChange} />
    );

    expect(screen.getByText("97.50, 4.00 → 98.30, 5.00")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("bbox-clear-button"));
    expect(onBboxChange).toHaveBeenCalledWith(null);
  });
});
