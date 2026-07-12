import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "@/context/LanguageContext";
import MapAddressSearch from "./MapAddressSearch";

const fitBoundsMock = vi.fn();
const geoJsonLog: unknown[] = [];

vi.mock("react-leaflet", () => ({
  useMap: () => ({ fitBounds: fitBoundsMock }),
  GeoJSON: (props: { data: unknown }) => {
    geoJsonLog.push(props.data);
    return <div data-testid="geojson-boundary" />;
  },
}));

vi.mock("@/api/client", () => ({
  fetchGeocodeSuggestions: vi.fn(),
}));

import { fetchGeocodeSuggestions } from "@/api/client";
import type { GeocodeResult } from "@/context/GISContext";

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

const SAMPLE_RESULT: GeocodeResult = {
  lat: 4.5,
  lng: 97.9,
  displayName: "Aceh Tamiang, Indonesia",
  bbox: [97.5, 4.0, 98.3, 5.0],
  polygon: null,
};

beforeEach(() => {
  vi.mocked(fetchGeocodeSuggestions).mockReset();
  fitBoundsMock.mockReset();
  geoJsonLog.length = 0;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("MapAddressSearch", () => {
  it("shows suggestions after typing at least 3 characters, debounced", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchGeocodeSuggestions).mockResolvedValue([SAMPLE_RESULT]);

    render(
      <Providers>
        <MapAddressSearch />
      </Providers>
    );

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), { target: { value: "Aceh" } });
    expect(fetchGeocodeSuggestions).not.toHaveBeenCalled();

    vi.advanceTimersByTime(300);

    await waitFor(() => expect(fetchGeocodeSuggestions).toHaveBeenCalledWith("Aceh"));
    expect(await screen.findByText("Aceh Tamiang, Indonesia")).toBeInTheDocument();
  });

  it("selecting a suggestion fits the map to its bounds and draws its boundary", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchGeocodeSuggestions).mockResolvedValue([SAMPLE_RESULT]);

    render(
      <Providers>
        <MapAddressSearch />
      </Providers>
    );

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), { target: { value: "Aceh" } });
    vi.advanceTimersByTime(300);
    fireEvent.click(await screen.findByText("Aceh Tamiang, Indonesia"));

    expect(fitBoundsMock).toHaveBeenCalledWith([
      [4.0, 97.5],
      [5.0, 98.3],
    ]);
    expect(screen.getByTestId("geojson-boundary")).toBeInTheDocument();
  });

  it("clearing the search removes the boundary", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchGeocodeSuggestions).mockResolvedValue([SAMPLE_RESULT]);

    render(
      <Providers>
        <MapAddressSearch />
      </Providers>
    );

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), { target: { value: "Aceh" } });
    vi.advanceTimersByTime(300);
    fireEvent.click(await screen.findByText("Aceh Tamiang, Indonesia"));
    expect(screen.getByTestId("geojson-boundary")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Clear search"));

    expect(screen.queryByTestId("geojson-boundary")).not.toBeInTheDocument();
  });
});
