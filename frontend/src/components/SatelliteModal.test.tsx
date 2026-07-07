import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEffect } from "react";
import { GISProvider, useGIS, type SearchResultItem } from "../context/GISContext";
import SatelliteModal, { findRelatedProducts } from "./SatelliteModal";

vi.mock("../api/client", () => ({
  fetchPreview: vi.fn(),
  getDownloadUrl: (productId: string) => `http://localhost:8000/api/download/${productId}`,
}));

import { fetchPreview } from "../api/client";

const SAMPLE_ITEM: SearchResultItem = {
  id: "p1",
  name: "S1A_IW_GRDH_1SDV_20260126.SAFE",
  productType: "SENTINEL_1_GRD",
  sensingTime: "2026-01-26T11:43:01Z",
  size: "1632MB",
  polarisation: "VV&VH",
  footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6]]] },
};

const SLC_SIBLING: SearchResultItem = {
  ...SAMPLE_ITEM,
  id: "p1-slc",
  name: "S1A_IW_SLC__1SDV_20260126.SAFE",
  productType: "SENTINEL_1_SLC",
  sensingTime: "2026-01-26T11:43:00Z", // 1s before the GRD - same pass
  size: "7171MB",
};

const UNRELATED_ITEM: SearchResultItem = {
  ...SAMPLE_ITEM,
  id: "p2",
  name: "S1A_IW_GRDH_1SDV_20260120.SAFE",
  sensingTime: "2026-01-20T23:12:21Z", // different pass entirely
};

function Setup({
  selected,
  results = [SAMPLE_ITEM],
}: {
  selected: boolean;
  results?: SearchResultItem[];
}) {
  const gis = useGIS();
  useEffect(() => {
    gis.setSearchResults(results, results.length);
    if (selected) {
      gis.selectProduct("p1");
    }
  }, []);
  return <SatelliteModal />;
}

beforeEach(() => {
  vi.mocked(fetchPreview).mockReset();
});

describe("SatelliteModal", () => {
  it("renders nothing when no product is selected", () => {
    render(
      <GISProvider>
        <Setup selected={false} />
      </GISProvider>
    );
    expect(screen.queryByText(/S1A_IW_GRDH_1SDV_20260126/i)).not.toBeInTheDocument();
  });

  it("shows product metadata when a footprint is selected", () => {
    render(
      <GISProvider>
        <Setup selected={true} />
      </GISProvider>
    );
    expect(screen.getByText(/S1A_IW_GRDH_1SDV_20260126\.SAFE/i)).toBeInTheDocument();
    expect(screen.getByText(/1632MB/i)).toBeInTheDocument();
    expect(screen.getByText(/VV&VH/i)).toBeInTheDocument();
  });

  it("'Unduh' link points at the backend download proxy with the product id", () => {
    render(
      <GISProvider>
        <Setup selected={true} />
      </GISProvider>
    );
    const link = screen.getByRole("link", { name: /unduh/i });
    expect(link).toHaveAttribute("href", "http://localhost:8000/api/download/p1");
  });

  it("'Lihat di Peta' fetches and stores the preview", async () => {
    vi.mocked(fetchPreview).mockResolvedValue({
      productId: "p1",
      tileUrl: "https://wms.test/process?access_token=tok",
      bounds: [[4, 95], [6, 98]],
    });

    function PreviewProbe() {
      const gis = useGIS();
      return <span data-testid="preview-url">{gis.previewData?.tileUrl ?? "none"}</span>;
    }

    render(
      <GISProvider>
        <Setup selected={true} />
        <PreviewProbe />
      </GISProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: /lihat di peta/i }));

    await waitFor(() =>
      expect(screen.getByTestId("preview-url").textContent).toBe(
        "https://wms.test/process?access_token=tok"
      )
    );
    expect(fetchPreview).toHaveBeenCalledWith("p1");
  });

  it("close button deselects the product", () => {
    render(
      <GISProvider>
        <Setup selected={true} />
      </GISProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: /tutup/i }));

    expect(screen.queryByText(/S1A_IW_GRDH_1SDV_20260126/i)).not.toBeInTheDocument();
  });

  it("shows every co-located product (GRD+SLC sharing a footprint), not just the clicked one", () => {
    render(
      <GISProvider>
        <Setup selected={true} results={[SAMPLE_ITEM, SLC_SIBLING, UNRELATED_ITEM]} />
      </GISProvider>
    );

    expect(screen.getByText(/Menampilkan 2 hasil/i)).toBeInTheDocument();
    expect(screen.getByText(/S1A_IW_GRDH_1SDV_20260126\.SAFE/i)).toBeInTheDocument();
    expect(screen.getByText(/S1A_IW_SLC__1SDV_20260126\.SAFE/i)).toBeInTheDocument();
    expect(screen.queryByText(/S1A_IW_GRDH_1SDV_20260120\.SAFE/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /lihat di peta/i })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /unduh/i })).toHaveLength(2);
  });
});

describe("findRelatedProducts", () => {
  it("includes items within 60s of the anchor's sensing time and excludes others", () => {
    const related = findRelatedProducts([SAMPLE_ITEM, SLC_SIBLING, UNRELATED_ITEM], SAMPLE_ITEM);
    expect(related.map((item) => item.id)).toEqual(["p1", "p1-slc"]);
  });

  it("returns just the anchor when nothing else is nearby in time", () => {
    const related = findRelatedProducts([SAMPLE_ITEM, UNRELATED_ITEM], SAMPLE_ITEM);
    expect(related.map((item) => item.id)).toEqual(["p1"]);
  });
});
