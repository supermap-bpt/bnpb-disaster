import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEffect, type ReactNode } from "react";
import { GISProvider, useGIS, type SearchResultItem } from "../context/GISContext";
import { LanguageProvider } from "../context/LanguageContext";
import Sidebar from "./Sidebar";

function Providers({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <GISProvider>{children}</GISProvider>
    </LanguageProvider>
  );
}

vi.mock("./FilterPanel", () => ({ default: () => <div data-testid="filter-panel" /> }));
vi.mock("./SearchBar", () => ({ default: () => <div data-testid="search-bar" /> }));
vi.mock("../api/client", () => ({
  fetchSearch: vi.fn(),
  getDownloadUrl: (id: string) => `http://localhost:8000/api/download/${id}`,
  getPreviewImageUrl: (id: string) => `http://localhost:8000/api/preview-image/${id}`,
}));

import { fetchSearch } from "../api/client";

function item(id: string): SearchResultItem {
  return {
    id,
    name: `${id}.SAFE`,
    productType: "SENTINEL_1_GRD",
    sensingTime: "2026-01-26T11:43:01Z",
    size: "1632MB",
    polarisation: "VV&VH",
    footprint: { type: "Polygon", coordinates: [] },
  };
}

function Seed({ results, total }: { results: SearchResultItem[]; total: number }) {
  const gis = useGIS();
  useEffect(() => {
    gis.setPlaceRing([
      [95.0, 4.0],
      [98.0, 4.0],
    ]);
    gis.setLastSearchFilter({
      productType: ["SENTINEL_1_GRD"],
      cloudCoverMax: 100,
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    gis.setSearchResults(results, total);
  }, []);
  return null;
}

beforeEach(() => {
  vi.mocked(fetchSearch).mockReset();
});

describe("Sidebar", () => {
  it("shows an empty-state message when there are no results yet", () => {
    render(
      <Providers>
        <Sidebar />
      </Providers>
    );

    expect(screen.getByText(/belum ada hasil/i)).toBeInTheDocument();
    expect(screen.getByText(/hasil pencarian/i)).toBeInTheDocument();
  });

  it("renders the address SearchBar above the filter panel", () => {
    render(
      <Providers>
        <Sidebar />
      </Providers>
    );

    expect(screen.getByTestId("search-bar")).toBeInTheDocument();
  });

  it("renders a card per result and the 'Showing X of Y' header", () => {
    render(
      <Providers>
        <Seed results={[item("p1"), item("p2")]} total={5} />
        <Sidebar />
      </Providers>
    );

    expect(screen.getByTestId("card-p1")).toBeInTheDocument();
    expect(screen.getByTestId("card-p2")).toBeInTheDocument();
    expect(screen.getByText(/menampilkan 2 dari 5 hasil/i)).toBeInTheDocument();
  });

  it("hides Load More when every result has already been loaded", () => {
    render(
      <Providers>
        <Seed results={[item("p1")]} total={1} />
        <Sidebar />
      </Providers>
    );

    expect(screen.queryByRole("button", { name: /muat lebih banyak/i })).not.toBeInTheDocument();
  });

  it("Load More fetches the next page (skip = current count) and appends", async () => {
    vi.mocked(fetchSearch).mockResolvedValue({ results: [item("p2")], total: 2 });

    render(
      <Providers>
        <Seed results={[item("p1")]} total={2} />
        <Sidebar />
      </Providers>
    );

    fireEvent.click(screen.getByRole("button", { name: /muat lebih banyak/i }));

    await waitFor(() => expect(screen.getByTestId("card-p2")).toBeInTheDocument());
    expect(fetchSearch).toHaveBeenCalledWith(
      { productType: ["SENTINEL_1_GRD"], cloudCoverMax: 100, dateFrom: "2026-01-01", dateUntil: "2026-02-01" },
      [
        [95.0, 4.0],
        [98.0, 4.0],
      ],
      1
    );
    expect(screen.getByText(/menampilkan 2 dari 2 hasil/i)).toBeInTheDocument();
  });
});
