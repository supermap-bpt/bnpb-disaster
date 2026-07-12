import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "@/context/LanguageContext";
import FloodPage from "./FloodPage";

type LatLng = { lat: number; lng: number };
let mapEventHandlers: Record<string, (event: { latlng: LatLng }) => void> = {};

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  GeoJSON: () => <div data-testid="geojson" />,
  ZoomControl: () => <div data-testid="zoom-control" />,
  useMap: () => ({
    fitBounds: vi.fn(),
    attributionControl: { setPrefix: vi.fn() },
    dragging: { enable: vi.fn(), disable: vi.fn() },
  }),
  useMapEvents: (handlers: Record<string, (event: { latlng: LatLng }) => void>) => {
    mapEventHandlers = handlers;
    return {
      fitBounds: vi.fn(),
      attributionControl: { setPrefix: vi.fn() },
      dragging: { enable: vi.fn(), disable: vi.fn() },
    };
  },
  Rectangle: () => <div data-testid="rectangle" />,
  Marker: () => <div data-testid="marker" />,
}));

vi.mock("@/api/client", () => ({
  fetchSavedSatellites: vi.fn(),
  fetchSavedSatelliteDetail: vi.fn(),
  deleteSavedSatellite: vi.fn(),
  retryFileDownload: vi.fn(),
  processFlood: vi.fn(),
  getSavedSatelliteThumbnailUrl: (path: string) => `http://localhost:8000/${path}`,
  getSavedSatelliteDownloadFileUrl: (id: string) => `http://localhost:8000/api/satellites/${id}/download-file`,
}));

import {
  deleteSavedSatellite,
  fetchSavedSatelliteDetail,
  fetchSavedSatellites,
  processFlood,
  retryFileDownload,
} from "@/api/client";

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

const SAMPLE_ITEM = {
  id: "sat-1",
  satelliteName: "Aceh Tamiang Flood 14 Jan",
  mission: "Sentinel-1",
  instrumentName: "SAR",
  polarisation: "VV",
  sensingTime: "2025-01-14T11:43:01Z",
  size: "1632MB",
  preview: null,
  savedAt: "2025-01-14T12:00:00Z",
  fileStatus: "completed" as const,
};

const FAILED_ITEM = { ...SAMPLE_ITEM, id: "sat-3", fileStatus: "failed" as const };

const SAMPLE_DETAIL = {
  ...SAMPLE_ITEM,
  productId: "p1",
  directoryPath: "storage/satellites/sat-1",
  summary: [{ label: "Name", value: "p1.SAFE" }],
  product: [],
  instrument: [],
  platform: [],
  other: [],
  downloadSingleFile: "p1.SAFE",
  footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6], [95, 6]]] },
  createdAt: "2025-01-14T12:00:00Z",
  updatedAt: "2025-01-14T12:00:00Z",
};

beforeEach(() => {
  vi.mocked(fetchSavedSatellites).mockReset();
  vi.mocked(fetchSavedSatelliteDetail).mockReset();
  vi.mocked(deleteSavedSatellite).mockReset();
  vi.mocked(retryFileDownload).mockReset();
  vi.mocked(processFlood).mockReset();
  mapEventHandlers = {};
  vi.stubGlobal("confirm", vi.fn(() => true));
});

describe("FloodPage", () => {
  it("shows the empty state when there are no saved satellites", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 10 });

    render(
      <Providers>
        <FloodPage />
      </Providers>
    );

    expect(await screen.findByText(/belum ada satelit tersimpan/i)).toBeInTheDocument();
  });

  it("lists saved satellites and renders the map column", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({
      items: [SAMPLE_ITEM],
      total: 1,
      page: 1,
      pageSize: 10,
    });

    render(
      <Providers>
        <FloodPage />
      </Providers>
    );

    expect(await screen.findByText("Aceh Tamiang Flood 14 Jan")).toBeInTheDocument();
    expect(screen.getByTestId("map-container")).toBeInTheDocument();
  });

  it("shows a failed badge with a Retry button, and retrying refetches the list", async () => {
    vi.mocked(fetchSavedSatellites)
      .mockResolvedValueOnce({ items: [FAILED_ITEM], total: 1, page: 1, pageSize: 10 })
      .mockResolvedValueOnce({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });
    vi.mocked(retryFileDownload).mockResolvedValue({ success: true, message: "File download restarted." });

    render(
      <Providers>
        <FloodPage />
      </Providers>
    );

    expect(await screen.findByText(/gagal mengunduh file/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /coba lagi/i }));

    await waitFor(() => expect(retryFileDownload).toHaveBeenCalledWith("sat-3"));
    await waitFor(() => expect(fetchSavedSatellites).toHaveBeenCalledTimes(2));
  });

  it("fetches detail and zooms the map when View on Map is clicked", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });
    vi.mocked(fetchSavedSatelliteDetail).mockResolvedValue(SAMPLE_DETAIL);

    render(
      <Providers>
        <FloodPage />
      </Providers>
    );

    await screen.findByText("Aceh Tamiang Flood 14 Jan");
    fireEvent.click(screen.getByRole("button", { name: /view on map/i }));

    await waitFor(() => expect(fetchSavedSatelliteDetail).toHaveBeenCalledWith("sat-1"));
    expect(await screen.findByTestId("geojson")).toBeInTheDocument();
  });

  describe("Flood AOI bounding box", () => {
    beforeEach(() => {
      vi.mocked(fetchSavedSatellites).mockResolvedValue({
        items: [SAMPLE_ITEM],
        total: 1,
        page: 1,
        pageSize: 10,
      });
    });

    async function selectOneReadyProduct() {
      fireEvent.click(screen.getByRole("button", { name: /^pilih$/i }));
    }

    it("shows the slow-full-scene confirmation when Process Flood is clicked with no bbox drawn", async () => {
      vi.stubGlobal("confirm", vi.fn(() => false));

      render(
        <Providers>
          <FloodPage />
        </Providers>
      );

      await screen.findByText("Aceh Tamiang Flood 14 Jan");
      await selectOneReadyProduct();
      fireEvent.click(screen.getByRole("button", { name: /proses banjir/i }));

      expect(window.confirm).toHaveBeenCalled();
      expect(processFlood).not.toHaveBeenCalled();
    });

    it("does not show the confirmation and processes directly when a bbox has been drawn", async () => {
      vi.mocked(processFlood).mockResolvedValue({
        id: "job-1",
        name: "Flood: Aceh Tamiang Flood 14 Jan",
        satelliteId: "sat-1",
        status: "pending",
        progress: 0,
        message: null,
        stage: null,
        stageIndex: 0,
        totalStages: 8,
        thresholdSigma0: 0.0137,
        hasResult: false,
        createdAt: "2025-01-14T12:00:00Z",
        updatedAt: "2025-01-14T12:00:00Z",
      });

      render(
        <Providers>
          <FloodPage />
        </Providers>
      );

      await screen.findByText("Aceh Tamiang Flood 14 Jan");
      await selectOneReadyProduct();

      fireEvent.click(screen.getByTestId("bbox-draw-button"));
      act(() => mapEventHandlers.mousedown({ latlng: { lat: 4.0, lng: 97.5 } }));
      act(() => mapEventHandlers.mouseup({ latlng: { lat: 5.0, lng: 98.3 } }));

      fireEvent.click(screen.getByRole("button", { name: /proses banjir/i }));

      await waitFor(() => expect(processFlood).toHaveBeenCalled());
      expect(window.confirm).not.toHaveBeenCalled();
      expect(processFlood).toHaveBeenCalledWith("sat-1", [97.5, 4.0, 98.3, 5.0]);
    });

    it("caps selection at one product - selecting a second is a no-op", async () => {
      vi.mocked(fetchSavedSatellites).mockResolvedValue({
        items: [SAMPLE_ITEM, { ...SAMPLE_ITEM, id: "sat-2", satelliteName: "Second scene" }],
        total: 2,
        page: 1,
        pageSize: 10,
      });

      render(
        <Providers>
          <FloodPage />
        </Providers>
      );

      await screen.findByText("Aceh Tamiang Flood 14 Jan");
      const selectButtons = screen.getAllByRole("button", { name: /^pilih$/i });
      fireEvent.click(selectButtons[0]);
      fireEvent.click(selectButtons[1]);

      expect(screen.getAllByRole("button", { name: /terpilih/i })).toHaveLength(1);
    });
  });
});
