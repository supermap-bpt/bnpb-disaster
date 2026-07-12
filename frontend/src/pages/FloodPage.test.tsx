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
  fetchFloodJobs: vi.fn(),
  deleteFloodJob: vi.fn(),
  fetchFloodPreview: vi.fn(),
  getSavedSatelliteThumbnailUrl: (path: string) => `http://localhost:8000/${path}`,
  getSavedSatelliteDownloadFileUrl: (id: string) => `http://localhost:8000/api/satellites/${id}/download-file`,
  getFloodResultUrl: (id: string) => `http://localhost:8000/api/flood/jobs/${id}/result`,
  getFloodPreviewImageUrl: (id: string) => `http://localhost:8000/api/flood/jobs/${id}/preview.png`,
  getFloodKmzUrl: (id: string) => `http://localhost:8000/api/flood/jobs/${id}/kmz`,
}));

import {
  deleteFloodJob,
  deleteSavedSatellite,
  fetchFloodJobs,
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
  vi.mocked(fetchFloodJobs).mockReset();
  vi.mocked(deleteFloodJob).mockReset();
  // Every test mounts FloodPage, which fetches the job list on mount - default
  // to an empty list so tests that don't care about the Jobs panel aren't
  // affected by an unhandled-rejection-shaped undefined return.
  vi.mocked(fetchFloodJobs).mockResolvedValue({ items: [], total: 0 });
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

  describe("Flood Jobs panel", () => {
    const PROCESSING_JOB = {
      id: "job-1",
      name: "Flood: Aceh Tamiang Flood 14 Jan",
      satelliteId: "sat-1",
      status: "processing" as const,
      progress: 42,
      message: "Subset… 50%",
      stage: "Subset",
      stageIndex: 3,
      totalStages: 8,
      thresholdSigma0: 0.0137,
      hasResult: false,
      createdAt: "2025-01-14T12:00:00Z",
      updatedAt: "2025-01-14T12:05:00Z",
    };

    beforeEach(() => {
      vi.mocked(fetchSavedSatellites).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 10 });
    });

    it("renders the 8-stage stepper reflecting a mid-pipeline job, with completed steps before stageIndex and one active step at stageIndex", async () => {
      vi.mocked(fetchFloodJobs).mockResolvedValue({ items: [PROCESSING_JOB], total: 1 });

      const { container } = render(
        <Providers>
          <FloodPage />
        </Providers>
      );

      expect(await screen.findByText("Pekerjaan Banjir")).toBeInTheDocument();
      expect(screen.getByText("Flood: Aceh Tamiang Flood 14 Jan")).toBeInTheDocument();

      const steps = container.querySelectorAll("ol li");
      expect(steps).toHaveLength(8);

      // stageIndex=3: steps 0,1,2 are done; step 3 is active; steps 4-7 are pending.
      const doneCount = Array.from(steps).filter((el) => el.className.includes("text-green-600")).length;
      const activeCount = Array.from(steps).filter((el) => el.className.includes("font-medium text-foreground")).length;
      expect(doneCount).toBe(3);
      expect(activeCount).toBe(1);
      expect(steps[3].className).toContain("font-medium text-foreground");
      expect(steps[0].className).toContain("text-green-600");
      expect(steps[7].className).toContain("text-muted-foreground");

      // Progress bar reflects job.progress.
      const bar = container.querySelector('[style*="width"]') as HTMLElement | null;
      expect(bar).not.toBeNull();
      expect(bar?.getAttribute("style")).toContain("42%");
    });

    it("deletes a job via the trash button after confirmation, and refetches the job list", async () => {
      vi.mocked(fetchFloodJobs)
        .mockResolvedValueOnce({ items: [PROCESSING_JOB], total: 1 })
        .mockResolvedValueOnce({ items: [], total: 0 });
      vi.mocked(deleteFloodJob).mockResolvedValue({ success: true });

      render(
        <Providers>
          <FloodPage />
        </Providers>
      );

      await screen.findByText("Flood: Aceh Tamiang Flood 14 Jan");
      fireEvent.click(screen.getByRole("button", { name: /hapus/i }));

      await waitFor(() => expect(deleteFloodJob).toHaveBeenCalledWith("job-1"));
      await waitFor(() => expect(fetchFloodJobs).toHaveBeenCalledTimes(2));
    });
  });
});
