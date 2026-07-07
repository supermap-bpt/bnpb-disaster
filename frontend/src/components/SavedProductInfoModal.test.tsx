import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "../context/LanguageContext";
import type { SavedSatelliteDetail } from "../api/client";
import SavedProductInfoModal from "./SavedProductInfoModal";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  GeoJSON: () => <div data-testid="geojson" />,
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    fetchProductAttributes: vi.fn(),
    getPreviewImageUrl: vi.fn(),
    getSavedSatelliteThumbnailUrl: (path: string) => `http://localhost:8000/${path}`,
    getSavedSatelliteDownloadFileUrl: (id: string) => `http://localhost:8000/api/satellites/${id}/download-file`,
  };
});

import { fetchProductAttributes, getPreviewImageUrl } from "../api/client";

const SAMPLE_DETAIL: SavedSatelliteDetail = {
  id: "sat-1",
  satelliteName: "Aceh Flood Jan 2025",
  mission: "Sentinel-1",
  instrumentName: "SAR",
  polarisation: "VV&VH",
  sensingTime: "2025-01-26T11:43:01Z",
  size: "1632MB",
  preview: "storage/satellites/sat-1/thumbnail.jpg",
  savedAt: "2025-01-26T12:00:00Z",
  fileStatus: "completed",
  productId: "p1",
  directoryPath: "storage/satellites/sat-1",
  summary: [{ label: "Name", value: "p1.SAFE" }],
  product: [{ label: "Absolute orbit number", value: "57694" }],
  instrument: [{ label: "Instrument short name", value: "SAR" }],
  platform: [{ label: "Platform short name", value: "SENTINEL-1" }],
  other: [{ label: "someField", value: "someValue" }],
  downloadSingleFile: "p1.SAFE",
  footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6], [95, 6]]] },
  createdAt: "2025-01-26T12:00:00Z",
  updatedAt: "2025-01-26T12:00:00Z",
};

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

describe("SavedProductInfoModal", () => {
  it("does not render when closed", () => {
    render(
      <Providers>
        <SavedProductInfoModal item={SAMPLE_DETAIL} open={false} onOpenChange={() => {}} />
      </Providers>
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders all sections directly from props, with no CDSE fetch calls", () => {
    render(
      <Providers>
        <SavedProductInfoModal item={SAMPLE_DETAIL} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    // Name appears twice by design: once in the Summary row, once as the
    // "Download single files" link text - both are real, not a bug.
    expect(screen.getAllByText("p1.SAFE").length).toBeGreaterThanOrEqual(2); // Summary row + Download link text
    expect(screen.getByText("57694")).toBeInTheDocument(); // Product row
    expect(screen.getAllByText("SAR").length).toBeGreaterThan(0); // Instrument row
    expect(screen.getAllByText("SENTINEL-1").length).toBeGreaterThan(0); // Platform row
    expect(screen.getByText("someField")).toBeInTheDocument(); // Other row
    expect(fetchProductAttributes).not.toHaveBeenCalled();
    expect(getPreviewImageUrl).not.toHaveBeenCalled();
  });

  it("shows the local preview thumbnail, not a live CDSE image", () => {
    render(
      <Providers>
        <SavedProductInfoModal item={SAMPLE_DETAIL} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    const image = screen.getByRole("img", { name: SAMPLE_DETAIL.satelliteName });
    expect(image).toHaveAttribute(
      "src",
      "http://localhost:8000/storage/satellites/sat-1/thumbnail.jpg"
    );
  });

  it("points the download link at the local download-file endpoint", () => {
    render(
      <Providers>
        <SavedProductInfoModal item={SAMPLE_DETAIL} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    const link = screen.getByRole("link", { name: SAMPLE_DETAIL.downloadSingleFile });
    expect(link).toHaveAttribute("href", "http://localhost:8000/api/satellites/sat-1/download-file");
  });

  it("disables the download link when the file is not yet cached", () => {
    const notReady = { ...SAMPLE_DETAIL, fileStatus: "downloading" as const };

    render(
      <Providers>
        <SavedProductInfoModal item={notReady} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    expect(screen.queryByRole("link", { name: notReady.downloadSingleFile })).not.toBeInTheDocument();
  });
});
