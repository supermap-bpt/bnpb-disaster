import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { GISProvider, useGIS } from "../context/GISContext";
import { LanguageProvider } from "../context/LanguageContext";
import SearchBar, { geocodeResultToAoiRing } from "./SearchBar";

function Providers({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <GISProvider>{children}</GISProvider>
    </LanguageProvider>
  );
}

vi.mock("../api/client", () => ({
  fetchGeocodeSuggestions: vi.fn(),
}));

import { fetchGeocodeSuggestions } from "../api/client";

const ACEH_TAMIANG = {
  lat: 4.325,
  lng: 97.985,
  displayName: "Aceh Tamiang, Aceh, Indonesia",
  bbox: [97.7283391, 3.8887805, 98.287468, 4.5354847] as [number, number, number, number],
  polygon: null,
};

function GeocodeProbe() {
  const gis = useGIS();
  return (
    <div>
      <span data-testid="display-name">{gis.geocodeResult?.displayName ?? "none"}</span>
      <span data-testid="aoi-points">{gis.placeRing?.length ?? "none"}</span>
      <span data-testid="address-query">{gis.addressQuery || "empty"}</span>
    </div>
  );
}

beforeEach(() => {
  vi.mocked(fetchGeocodeSuggestions).mockReset();
});

describe("geocodeResultToAoiRing", () => {
  it("builds a rectangle ring from bbox when no polygon is available", () => {
    expect(geocodeResultToAoiRing(ACEH_TAMIANG)).toEqual([
      [97.7283391, 3.8887805],
      [98.287468, 3.8887805],
      [98.287468, 4.5354847],
      [97.7283391, 4.5354847],
    ]);
  });

  it("uses the administrative boundary polygon when available", () => {
    const withPolygon = {
      ...ACEH_TAMIANG,
      polygon: [
        [97.8, 4.0],
        [98.0, 4.0],
        [97.9, 4.2],
      ],
    };
    expect(geocodeResultToAoiRing(withPolygon)).toEqual([
      [97.8, 4.0],
      [98.0, 4.0],
      [97.9, 4.2],
    ]);
  });
});

describe("SearchBar", () => {
  it("debounces typing and shows a dropdown of address suggestions", async () => {
    vi.mocked(fetchGeocodeSuggestions).mockResolvedValue([
      ACEH_TAMIANG,
      { ...ACEH_TAMIANG, lat: 4.4, lng: 98.0, displayName: "Aceh Tamiang Regency, Indonesia" },
    ]);

    render(
      <Providers>
        <SearchBar />
      </Providers>
    );

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), {
      target: { value: "Aceh Tam" },
    });

    expect(fetchGeocodeSuggestions).not.toHaveBeenCalled();

    await waitFor(() => expect(fetchGeocodeSuggestions).toHaveBeenCalledWith("Aceh Tam"));
    expect(await screen.findByText("Aceh Tamiang, Aceh, Indonesia")).toBeInTheDocument();
    expect(screen.getByText("Aceh Tamiang Regency, Indonesia")).toBeInTheDocument();
  });

  it("does not search for queries shorter than 3 characters", async () => {
    render(
      <Providers>
        <SearchBar />
      </Providers>
    );

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), { target: { value: "Ac" } });

    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(fetchGeocodeSuggestions).not.toHaveBeenCalled();
  });

  it("clicking a suggestion stores it and its AOI ring in GISContext, and closes the dropdown", async () => {
    vi.mocked(fetchGeocodeSuggestions).mockResolvedValue([ACEH_TAMIANG]);

    render(
      <Providers>
        <SearchBar />
        <GeocodeProbe />
      </Providers>
    );

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), {
      target: { value: "Aceh Tamiang" },
    });

    const suggestion = await screen.findByText("Aceh Tamiang, Aceh, Indonesia");
    fireEvent.click(suggestion);

    expect(screen.getByTestId("display-name").textContent).toBe("Aceh Tamiang, Aceh, Indonesia");
    expect(screen.getByTestId("aoi-points").textContent).toBe("4");
    expect(screen.getByTestId("address-query").textContent).toBe("Aceh Tamiang, Aceh, Indonesia");
    expect(
      screen.queryByRole("button", { name: "Aceh Tamiang, Aceh, Indonesia" })
    ).not.toBeInTheDocument();
  });

  it("pressing Enter selects the first suggestion", async () => {
    vi.mocked(fetchGeocodeSuggestions).mockResolvedValue([ACEH_TAMIANG]);

    render(
      <Providers>
        <SearchBar />
        <GeocodeProbe />
      </Providers>
    );

    const input = screen.getByPlaceholderText(/cari alamat/i);
    fireEvent.change(input, { target: { value: "Aceh Tamiang" } });
    await screen.findByText("Aceh Tamiang, Aceh, Indonesia");

    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByTestId("display-name").textContent).toBe("Aceh Tamiang, Aceh, Indonesia");
  });

  it("shows an error message when the suggestions request fails", async () => {
    vi.mocked(fetchGeocodeSuggestions).mockRejectedValue(new Error("Geocoding upstream error"));

    render(
      <Providers>
        <SearchBar />
      </Providers>
    );

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), {
      target: { value: "nowhere12345" },
    });

    expect(await screen.findByText("Geocoding upstream error")).toBeInTheDocument();
  });

  it("mirrors the input text into GISContext.addressQuery, and clears it on Clear", async () => {
    function AddressProbe() {
      const gis = useGIS();
      return <span data-testid="address-query">{gis.addressQuery || "empty"}</span>;
    }

    render(
      <Providers>
        <SearchBar />
        <AddressProbe />
      </Providers>
    );

    expect(screen.getByTestId("address-query").textContent).toBe("empty");

    fireEvent.change(screen.getByPlaceholderText(/cari alamat/i), {
      target: { value: "Aceh Tamiang" },
    });
    expect(screen.getByTestId("address-query").textContent).toBe("Aceh Tamiang");

    fireEvent.click(screen.getByLabelText("Clear search"));
    expect(screen.getByTestId("address-query").textContent).toBe("empty");
  });
});
