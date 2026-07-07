import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "../context/LanguageContext";
import type { SearchResultItem } from "../context/GISContext";
import ProductInfoModal from "./ProductInfoModal";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  GeoJSON: () => <div data-testid="geojson" />,
}));

vi.mock("../api/client", () => ({
  fetchProductAttributes: vi.fn(),
  getDownloadUrl: (id: string) => `http://localhost:8000/api/download/${id}`,
  getPreviewImageUrl: (id: string) => `http://localhost:8000/api/preview-image/${id}`,
}));

import { fetchProductAttributes } from "../api/client";

const SAMPLE_ITEM: SearchResultItem = {
  id: "p1",
  name: "S1A_IW_GRDH_1SDV_20260126.SAFE",
  productType: "SENTINEL_1_GRD",
  sensingTime: "2026-01-26T11:43:01Z",
  size: "1632MB",
  polarisation: "VV&VH",
  footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6], [95, 6]]] },
};

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

beforeEach(() => {
  vi.mocked(fetchProductAttributes).mockReset();
});

describe("ProductInfoModal", () => {
  it("does not fetch attributes or render content while closed", () => {
    render(
      <Providers>
        <ProductInfoModal item={SAMPLE_ITEM} open={false} onOpenChange={() => {}} />
      </Providers>
    );

    expect(fetchProductAttributes).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("always shows Name/Size/Sensing time in Summary, even with no attributes", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([]);

    render(
      <Providers>
        <ProductInfoModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    await waitFor(() => expect(fetchProductAttributes).toHaveBeenCalledWith("p1"));
    // Name appears twice by design: once in the Summary row, once as the
    // "Download single files" link text - both are real, not a bug.
    expect((await screen.findAllByText(SAMPLE_ITEM.name)).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("1632MB")).toBeInTheDocument();
    expect(screen.getByText("2026-01-26T11:43:01Z")).toBeInTheDocument();
  });

  it("groups known attributes into Product/Instrument/Platform sections", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([
      { name: "orbitDirection", value: "DESCENDING" },
      { name: "instrumentShortName", value: "SAR" },
      { name: "platformShortName", value: "SENTINEL-1" },
    ]);

    render(
      <Providers>
        <ProductInfoModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    expect(await screen.findByText("DESCENDING")).toBeInTheDocument();
    expect(screen.getAllByText("SAR").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SENTINEL-1").length).toBeGreaterThan(0);
    expect(screen.getByText("Orbit direction")).toBeInTheDocument();
  });

  it("shows unmapped attributes under an Other section instead of dropping them", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([
      { name: "someBrandNewCdseField", value: "weird-value" },
    ]);

    render(
      <Providers>
        <ProductInfoModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    expect(await screen.findByText("Other")).toBeInTheDocument();
    expect(screen.getByText("someBrandNewCdseField")).toBeInTheDocument();
    expect(screen.getByText("weird-value")).toBeInTheDocument();
  });

  it("shows an error message when the attributes request fails", async () => {
    vi.mocked(fetchProductAttributes).mockRejectedValue(new Error("No cached data for product p1."));

    render(
      <Providers>
        <ProductInfoModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    expect(await screen.findByText("No cached data for product p1.")).toBeInTheDocument();
  });

  it("shows the single-file download link with the real product name", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([]);

    render(
      <Providers>
        <ProductInfoModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    await waitFor(() => expect(fetchProductAttributes).toHaveBeenCalled());
    const link = screen.getByRole("link", { name: SAMPLE_ITEM.name });
    expect(link).toHaveAttribute("href", "http://localhost:8000/api/download/p1");
  });

  it("maps the cloudCover attribute to a friendly label", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([{ name: "cloudCover", value: "12.5" }]);

    render(
      <Providers>
        <ProductInfoModal
          item={{ ...SAMPLE_ITEM, productType: "SENTINEL_2_L2A" }}
          open={true}
          onOpenChange={() => {}}
        />
      </Providers>
    );

    expect(await screen.findByText("Cloud cover")).toBeInTheDocument();
    expect(screen.getByText("12.5")).toBeInTheDocument();
  });

  it("shows a thumbnail for Sentinel-2 L2A items", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([]);

    render(
      <Providers>
        <ProductInfoModal
          item={{ ...SAMPLE_ITEM, productType: "SENTINEL_2_L2A", id: "p2" }}
          open={true}
          onOpenChange={() => {}}
        />
      </Providers>
    );

    await waitFor(() => expect(fetchProductAttributes).toHaveBeenCalled());
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "http://localhost:8000/api/preview-image/p2"
    );
  });
});
