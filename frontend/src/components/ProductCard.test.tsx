import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useEffect, type ReactNode } from "react";
import { GISProvider, useGIS, type SearchResultItem } from "../context/GISContext";
import { LanguageProvider } from "../context/LanguageContext";
import ProductCard from "./ProductCard";

function Providers({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <GISProvider>{children}</GISProvider>
    </LanguageProvider>
  );
}

vi.mock("../api/client", () => ({
  getDownloadUrl: (productId: string) => `http://localhost:8000/api/download/${productId}`,
  getPreviewImageUrl: (productId: string) => `http://localhost:8000/api/preview-image/${productId}`,
  fetchProductAttributes: vi.fn().mockResolvedValue([]),
  saveSatellite: vi.fn(),
}));

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  GeoJSON: () => <div data-testid="geojson" />,
}));

const SAMPLE_ITEM: SearchResultItem = {
  id: "p1",
  name: "S1A_IW_GRDH_1SDV_20260126.SAFE",
  productType: "SENTINEL_1_GRD",
  sensingTime: "2026-01-26T11:43:01Z",
  size: "1632MB",
  polarisation: "VV&VH",
  footprint: { type: "Polygon", coordinates: [] },
};

const SENTINEL2_ITEM: SearchResultItem = {
  id: "p2",
  name: "S2A_MSIL2A_20260126T114301.SAFE",
  productType: "SENTINEL_2_L2A",
  sensingTime: "2026-01-26T11:43:01Z",
  size: "734MB",
  polarisation: "N/A",
  cloudCoverPercentage: 12.5,
  footprint: { type: "Polygon", coordinates: [] },
};

const SENTINEL3_ITEM: SearchResultItem = {
  id: "p5",
  name: "S3A_SL_2_LST____20260126T114301.SEN3",
  productType: "SENTINEL_3_SLSTR_L2_LST",
  sensingTime: "2026-01-26T11:43:01Z",
  size: "300MB",
  polarisation: "N/A",
  footprint: { type: "Polygon", coordinates: [] },
};

function SelectFirst({ select }: { select: boolean }) {
  const gis = useGIS();
  useEffect(() => {
    if (select) gis.selectProduct("p1");
  }, [select]);
  return null;
}

describe("ProductCard", () => {
  it("shows mission/instrument/type/polarisation/sensing time/size", () => {
    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    expect(screen.getByText("Sentinel-1")).toBeInTheDocument();
    expect(screen.getByText("SAR")).toBeInTheDocument();
    expect(screen.getByText("Level 1-GRD")).toBeInTheDocument();
    expect(screen.getByText("VV&VH")).toBeInTheDocument();
    expect(screen.getByText("2026-01-26T11:43:01Z")).toBeInTheDocument();
    expect(screen.getByText("1632MB")).toBeInTheDocument();
  });

  it("'View on Map' selects the product", () => {
    function SelectedProbe() {
      const gis = useGIS();
      return <span data-testid="selected">{gis.selectedProductId ?? "none"}</span>;
    }

    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
        <SelectedProbe />
      </Providers>
    );

    fireEvent.click(screen.getByRole("button", { name: /view on map/i }));
    expect(screen.getByTestId("selected").textContent).toBe("p1");
  });

  it("button becomes 'Hapus dari Peta' once selected, and clicking it clears the selection", () => {
    function SelectedProbe() {
      const gis = useGIS();
      return <span data-testid="selected">{gis.selectedProductId ?? "none"}</span>;
    }

    render(
      <Providers>
        <SelectFirst select={true} />
        <ProductCard item={SAMPLE_ITEM} />
        <SelectedProbe />
      </Providers>
    );

    expect(screen.getByTestId("selected").textContent).toBe("p1");
    expect(screen.queryByRole("button", { name: /^view on map$/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /hapus dari peta/i }));

    expect(screen.getByTestId("selected").textContent).toBe("none");
    expect(screen.getByRole("button", { name: /^view on map$/i })).toBeInTheDocument();
  });

  it("Download link points at the backend download proxy with the product id", () => {
    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      "http://localhost:8000/api/download/p1"
    );
  });

  it("highlights the card when it is the selected product", () => {
    render(
      <Providers>
        <SelectFirst select={true} />
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    expect(screen.getByTestId("card-p1").className).toContain("border-primary");
  });

  it("hovering the card sets hoveredProductId, leaving clears it", () => {
    function HoverProbe() {
      const gis = useGIS();
      return <span data-testid="hovered">{gis.hoveredProductId ?? "none"}</span>;
    }

    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
        <HoverProbe />
      </Providers>
    );

    fireEvent.mouseEnter(screen.getByTestId("card-p1"));
    expect(screen.getByTestId("hovered").textContent).toBe("p1");

    fireEvent.mouseLeave(screen.getByTestId("card-p1"));
    expect(screen.getByTestId("hovered").textContent).toBe("none");
  });

  it("shows a real thumbnail image for GRD products", () => {
    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    expect(screen.getByRole("img", { name: SAMPLE_ITEM.name })).toHaveAttribute(
      "src",
      "http://localhost:8000/api/preview-image/p1"
    );
  });

  it("shows the placeholder (no image attempt) for SLC products", () => {
    const slcItem: SearchResultItem = { ...SAMPLE_ITEM, productType: "SENTINEL_1_SLC" };
    render(
      <Providers>
        <ProductCard item={slcItem} />
      </Providers>
    );

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("No Preview")).toBeInTheDocument();
  });

  it("falls back to the placeholder if the thumbnail image fails to load", () => {
    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    fireEvent.error(screen.getByRole("img", { name: SAMPLE_ITEM.name }));

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("No Preview")).toBeInTheDocument();
  });

  it("reserves disabled Metadata/Workspace/Favorite actions", () => {
    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    expect(screen.getByRole("button", { name: /metadata/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /workspace/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /favorite/i })).toBeDisabled();
  });

  it("Info button opens the Product Info modal", async () => {
    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^info$/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /product info/i })).toBeInTheDocument();
  });

  it("Save button opens the Save Satellite modal", async () => {
    render(
      <Providers>
        <ProductCard item={SAMPLE_ITEM} />
      </Providers>
    );

    expect(screen.queryByText(/simpan satelit/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^simpan$/i }));

    expect(await screen.findByText(/simpan satelit/i)).toBeInTheDocument();
  });

  it("shows Sentinel-2/MSI mission/instrument and a cloud cover row instead of polarisation", () => {
    render(
      <Providers>
        <ProductCard item={SENTINEL2_ITEM} />
      </Providers>
    );

    expect(screen.getByText("Sentinel-2")).toBeInTheDocument();
    expect(screen.getByText("MSI")).toBeInTheDocument();
    expect(screen.getByText("L2A")).toBeInTheDocument();
    expect(screen.getByText("13%")).toBeInTheDocument();
    expect(screen.queryByText("N/A")).not.toBeInTheDocument();
  });

  it("shows a real thumbnail for Sentinel-2 L2A", () => {
    render(
      <Providers>
        <ProductCard item={SENTINEL2_ITEM} />
      </Providers>
    );

    expect(screen.getByRole("img", { name: SENTINEL2_ITEM.name })).toHaveAttribute(
      "src",
      "http://localhost:8000/api/preview-image/p2"
    );
  });

  it("shows the placeholder for Sentinel-2 L1C", () => {
    const l1cItem: SearchResultItem = { ...SENTINEL2_ITEM, productType: "SENTINEL_2_L1C", id: "p3" };
    render(
      <Providers>
        <ProductCard item={l1cItem} />
      </Providers>
    );

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("No Preview")).toBeInTheDocument();
  });

  it("shows N/A (not 0% or a crash) when cloudCoverPercentage is null", () => {
    const nullCloudItem: SearchResultItem = { ...SENTINEL2_ITEM, cloudCoverPercentage: null, id: "p4" };
    render(
      <Providers>
        <ProductCard item={nullCloudItem} />
      </Providers>
    );

    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("shows Sentinel-3/SLSTR mission/instrument/label and no polarisation or cloud cover row", () => {
    render(
      <Providers>
        <ProductCard item={SENTINEL3_ITEM} />
      </Providers>
    );

    expect(screen.getByText("Sentinel-3")).toBeInTheDocument();
    expect(screen.getByText("SLSTR")).toBeInTheDocument();
    expect(screen.getByText("Level-2 LST")).toBeInTheDocument();
    expect(screen.queryByText("N/A")).not.toBeInTheDocument();
    expect(screen.queryByText(/polarisation/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cloud cover/i)).not.toBeInTheDocument();
  });

  it("shows the placeholder (no image attempt) for Sentinel-3 SLSTR L2 WST", () => {
    const wstItem: SearchResultItem = { ...SENTINEL3_ITEM, productType: "SENTINEL_3_SLSTR_L2_WST", id: "p6" };
    render(
      <Providers>
        <ProductCard item={wstItem} />
      </Providers>
    );

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("No Preview")).toBeInTheDocument();
    expect(screen.getByText("Level-2 WST")).toBeInTheDocument();
  });
});
