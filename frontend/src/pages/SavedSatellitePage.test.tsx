import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "@/context/LanguageContext";
import SavedSatellitePage from "./SavedSatellitePage";

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
  processLandslide: vi.fn(),
  getSavedSatelliteThumbnailUrl: (path: string) => `http://localhost:8000/${path}`,
  getSavedSatelliteDownloadFileUrl: (id: string) => `http://localhost:8000/api/satellites/${id}/download-file`,
}));

import {
  deleteSavedSatellite,
  fetchSavedSatelliteDetail,
  fetchSavedSatellites,
  processLandslide,
  retryFileDownload,
} from "@/api/client";

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

const SAMPLE_ITEM = {
  id: "sat-1",
  satelliteName: "Aceh Flood Jan 2025",
  mission: "Sentinel-1",
  instrumentName: "SAR",
  polarisation: "VV&VH",
  sensingTime: "2025-01-26T11:43:01Z",
  size: "1632MB",
  preview: null,
  savedAt: "2025-01-26T12:00:00Z",
  fileStatus: "completed" as const,
};

const DOWNLOADING_ITEM = { ...SAMPLE_ITEM, id: "sat-2", fileStatus: "downloading" as const };
const FAILED_ITEM = { ...SAMPLE_ITEM, id: "sat-3", fileStatus: "failed" as const };
const SAMPLE_ITEM_2 = { ...SAMPLE_ITEM, id: "sat-4", satelliteName: "Aceh Flood Feb 2025" };

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
  createdAt: "2025-01-26T12:00:00Z",
  updatedAt: "2025-01-26T12:00:00Z",
};

beforeEach(() => {
  vi.mocked(fetchSavedSatellites).mockReset();
  vi.mocked(fetchSavedSatelliteDetail).mockReset();
  vi.mocked(deleteSavedSatellite).mockReset();
  vi.mocked(retryFileDownload).mockReset();
  vi.mocked(processLandslide).mockReset();
  mapEventHandlers = {};
  vi.stubGlobal("confirm", vi.fn(() => true));
});

describe("SavedSatellitePage", () => {
  it("shows the empty state when there are no saved satellites", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 10 });

    render(
      <Providers>
        <SavedSatellitePage />
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
        <SavedSatellitePage />
      </Providers>
    );

    expect(await screen.findByText("Aceh Flood Jan 2025")).toBeInTheDocument();
    expect(screen.getByTestId("map-container")).toBeInTheDocument();
  });

  it("deletes a satellite and refetches the list", async () => {
    vi.mocked(fetchSavedSatellites)
      .mockResolvedValueOnce({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 10 });
    vi.mocked(deleteSavedSatellite).mockResolvedValue({ success: true, message: "deleted" });

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    await screen.findByText("Aceh Flood Jan 2025");
    fireEvent.click(screen.getByRole("button", { name: /hapus/i }));

    await waitFor(() => expect(deleteSavedSatellite).toHaveBeenCalledWith("sat-1"));
    await waitFor(() => expect(fetchSavedSatellites).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/belum ada satelit tersimpan/i)).toBeInTheDocument();
  });

  it("shows a failed badge with a Retry button, and retrying refetches the list", async () => {
    vi.mocked(fetchSavedSatellites)
      .mockResolvedValueOnce({ items: [FAILED_ITEM], total: 1, page: 1, pageSize: 10 })
      .mockResolvedValueOnce({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });
    vi.mocked(retryFileDownload).mockResolvedValue({ success: true, message: "File download restarted." });

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    expect(await screen.findByText(/gagal mengunduh file/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /coba lagi/i }));

    await waitFor(() => expect(retryFileDownload).toHaveBeenCalledWith("sat-3"));
    await waitFor(() => expect(fetchSavedSatellites).toHaveBeenCalledTimes(2));
  });

  it("filters by name, resetting to page 1", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    await screen.findByText("Aceh Flood Jan 2025");
    fireEvent.change(screen.getByPlaceholderText(/cari nama satelit/i), { target: { value: "Aceh" } });

    await waitFor(
      () =>
        expect(fetchSavedSatellites).toHaveBeenLastCalledWith(
          expect.objectContaining({ name: "Aceh", page: 1 })
        ),
      { timeout: 1000 }
    );
  });

  it("shows pagination controls and requests the next page on click", async () => {
    vi.mocked(fetchSavedSatellites)
      .mockResolvedValueOnce({ items: [SAMPLE_ITEM], total: 15, page: 1, pageSize: 10 })
      .mockResolvedValueOnce({ items: [SAMPLE_ITEM], total: 15, page: 2, pageSize: 10 });

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    await screen.findByText("Aceh Flood Jan 2025");
    fireEvent.click(screen.getByRole("button", { name: /selanjutnya/i }));

    await waitFor(() =>
      expect(fetchSavedSatellites).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    );
  });

  it("fetches detail and zooms the map when View on Map is clicked", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });
    vi.mocked(fetchSavedSatelliteDetail).mockResolvedValue(SAMPLE_DETAIL);

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    await screen.findByText("Aceh Flood Jan 2025");
    fireEvent.click(screen.getByRole("button", { name: /view on map/i }));

    await waitFor(() => expect(fetchSavedSatelliteDetail).toHaveBeenCalledWith("sat-1"));
    expect(await screen.findByTestId("geojson")).toBeInTheDocument();
  });

  it("opens Product Info with the fetched detail", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });
    vi.mocked(fetchSavedSatelliteDetail).mockResolvedValue(SAMPLE_DETAIL);

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    await screen.findByText("Aceh Flood Jan 2025");
    fireEvent.click(screen.getByRole("button", { name: /product info/i }));

    await waitFor(() => expect(fetchSavedSatelliteDetail).toHaveBeenCalledWith("sat-1"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("disables the Download button when the file is not yet cached", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({
      items: [DOWNLOADING_ITEM],
      total: 1,
      page: 1,
      pageSize: 10,
    });

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    await screen.findByText("Aceh Flood Jan 2025");
    const downloadLink = screen.queryByRole("link", { name: /download/i });
    expect(downloadLink).not.toBeInTheDocument();
  });

  it("enables the Download button pointing at the local file endpoint when the file is cached", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    const downloadLink = await screen.findByRole("link", { name: /download/i });
    expect(downloadLink).toHaveAttribute(
      "href",
      "http://localhost:8000/api/satellites/sat-1/download-file"
    );
  });

  it("switches the View on Map button to the secondary style once this card is the one shown on the map", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });
    vi.mocked(fetchSavedSatelliteDetail).mockResolvedValue(SAMPLE_DETAIL);

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    const viewOnMapButton = await screen.findByRole("button", { name: /view on map/i });
    expect(viewOnMapButton.className).toContain("bg-primary");

    fireEvent.click(viewOnMapButton);

    await waitFor(() => expect(fetchSavedSatelliteDetail).toHaveBeenCalledWith("sat-1"));
    expect(viewOnMapButton.className).toContain("bg-secondary");
  });

  it("toggles View on Map to Remove from Map and back, clearing the map selection without re-fetching", async () => {
    vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [SAMPLE_ITEM], total: 1, page: 1, pageSize: 10 });
    vi.mocked(fetchSavedSatelliteDetail).mockResolvedValue(SAMPLE_DETAIL);

    render(
      <Providers>
        <SavedSatellitePage />
      </Providers>
    );

    const toggleButton = await screen.findByRole("button", { name: /view on map/i });
    fireEvent.click(toggleButton);

    await waitFor(() => expect(fetchSavedSatelliteDetail).toHaveBeenCalledWith("sat-1"));
    expect(await screen.findByTestId("geojson")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /hapus dari peta/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /hapus dari peta/i }));

    await waitFor(() => expect(screen.queryByTestId("geojson")).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: /view on map/i })).toBeInTheDocument();
    expect(fetchSavedSatelliteDetail).toHaveBeenCalledTimes(1);
  });

  describe("Landslide AOI bounding box", () => {
    async function renderWithTwoReadyProducts() {
      vi.mocked(fetchSavedSatellites).mockResolvedValue({
        items: [SAMPLE_ITEM, SAMPLE_ITEM_2],
        total: 2,
        page: 1,
        pageSize: 10,
      });

      render(
        <Providers>
          <SavedSatellitePage />
        </Providers>
      );

      await screen.findByText("Aceh Flood Jan 2025");
      const selectButtons = screen.getAllByRole("button", { name: /^pilih$/i });
      fireEvent.click(selectButtons[0]);
      fireEvent.click(selectButtons[1]);
    }

    it("shows the slow-full-scene confirmation when Process Landslide is clicked with no bbox drawn", async () => {
      vi.stubGlobal("confirm", vi.fn(() => false));
      await renderWithTwoReadyProducts();

      fireEvent.click(screen.getByRole("button", { name: /proses longsor/i }));

      expect(window.confirm).toHaveBeenCalled();
      expect(processLandslide).not.toHaveBeenCalled();
    });

    it("does not show the confirmation and processes directly when a bbox has been drawn", async () => {
      vi.mocked(processLandslide).mockResolvedValue({
        id: "job-1",
        name: "Landslide: Aceh Flood Jan 2025 -> Aceh Flood Feb 2025",
        preSatelliteId: "sat-1",
        postSatelliteId: "sat-4",
        status: "pending",
        progress: 0,
        message: null,
        stage: null,
        stageIndex: 0,
        totalStages: 7,
        thresholdDb: -2,
        hasResult: false,
        createdAt: "2025-01-26T12:00:00Z",
        updatedAt: "2025-01-26T12:00:00Z",
      });
      await renderWithTwoReadyProducts();

      // Arm the draw tool, then simulate a real click-drag via the captured
      // useMapEvents handlers - this exercises the real MapBboxDrawTool ->
      // real SavedSatelliteMap -> real SavedSatellitePage bbox state wiring.
      fireEvent.click(screen.getByTestId("bbox-draw-button"));
      act(() => mapEventHandlers.mousedown({ latlng: { lat: 4.0, lng: 97.5 } }));
      act(() => mapEventHandlers.mouseup({ latlng: { lat: 5.0, lng: 98.3 } }));

      fireEvent.click(screen.getByRole("button", { name: /proses longsor/i }));

      await waitFor(() => expect(processLandslide).toHaveBeenCalled());
      expect(window.confirm).not.toHaveBeenCalled();
      expect(processLandslide).toHaveBeenCalledWith("sat-1", "sat-4", [97.5, 4.0, 98.3, 5.0]);
    });

    it("no longer renders a manual AOI text input", async () => {
      await renderWithTwoReadyProducts();

      expect(screen.queryByPlaceholderText(/minLon/i)).not.toBeInTheDocument();
    });
  });
});
