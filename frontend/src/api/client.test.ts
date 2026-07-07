import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchGeocodeSuggestions,
  fetchPreview,
  fetchProductAttributes,
  fetchSearch,
  getDownloadUrl,
  getPreviewImageUrl,
} from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("fetchGeocodeSuggestions returns parsed results list on success", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          { lat: 4.325, lng: 97.985, displayName: "Aceh Tamiang" },
          { lat: 4.4, lng: 98.0, displayName: "Aceh Tamiang Regency" },
        ],
      }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await fetchGeocodeSuggestions("Aceh Tamiang");

    expect(result).toHaveLength(2);
    expect(result[0].lat).toBe(4.325);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/geocode?q=Aceh%20Tamiang")
    );
  });

  it("fetchGeocodeSuggestions throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => ({ detail: "upstream error" }) })
    );

    await expect(fetchGeocodeSuggestions("nowhere")).rejects.toThrow("upstream error");
  });

  it("fetchSearch repeats productType param, serializes the AOI ring, and returns results + total", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [], total: 0 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await fetchSearch(
      {
        productType: ["SENTINEL_1_SLC", "SENTINEL_1_GRD"],
        cloudCoverMax: 100,
        dateFrom: "2026-01-01",
        dateUntil: "2026-02-01",
      },
      [
        [95.0, 4.0],
        [98.0, 4.0],
        [98.0, 6.0],
        [95.0, 6.0],
      ]
    );

    expect(result).toEqual({ results: [], total: 0 });
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/search?");
    expect(calledUrl).toContain("productType=SENTINEL_1_SLC");
    expect(calledUrl).toContain("productType=SENTINEL_1_GRD");
    expect(calledUrl).toContain("aoi=95%2C4%2C98%2C4%2C98%2C6%2C95%2C6");
    expect(calledUrl).toContain("skip=0");
  });

  it("fetchSearch sends an explicit skip for Load More pagination", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [], total: 0 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await fetchSearch(
      { productType: ["SENTINEL_1_GRD"], cloudCoverMax: 100, dateFrom: "2026-01-01", dateUntil: "2026-02-01" },
      [[95.0, 4.0], [98.0, 4.0]],
      50
    );

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("skip=50");
  });

  it("fetchSearch includes cloudCoverMax in the query string", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [], total: 0 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await fetchSearch(
      {
        productType: ["SENTINEL_2_L2A"],
        cloudCoverMax: 30,
        dateFrom: "2026-01-01",
        dateUntil: "2026-02-01",
      },
      [
        [95.0, 4.0],
        [98.0, 4.0],
        [98.0, 6.0],
        [95.0, 6.0],
      ]
    );

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("cloudCoverMax=30");
  });

  it("fetchPreview returns parsed preview data with tileUrl made absolute", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          productId: "p1",
          // Backend returns a relative path - this is the real contract now.
          tileUrl: "/api/preview-image/p1",
          bounds: [[4.0, 95.0], [6.0, 98.0]],
        }),
      })
    );

    const preview = await fetchPreview("p1");

    expect(preview.productId).toBe("p1");
    expect(preview.bounds).toEqual([[4.0, 95.0], [6.0, 98.0]]);
    expect(preview.tileUrl).toMatch(/\/api\/preview-image\/p1$/);
    expect(preview.tileUrl).toMatch(/^https?:\/\//);
  });

  it("getDownloadUrl builds a backend download proxy URL", () => {
    expect(getDownloadUrl("p1")).toMatch(/\/api\/download\/p1$/);
  });

  it("getPreviewImageUrl builds a backend preview-image proxy URL", () => {
    expect(getPreviewImageUrl("p1")).toMatch(/\/api\/preview-image\/p1$/);
  });

  it("fetchProductAttributes returns the parsed attribute list", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        attributes: [
          { name: "orbitDirection", value: "DESCENDING" },
          { name: "operationalMode", value: "IW" },
        ],
      }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const attributes = await fetchProductAttributes("p1");

    expect(attributes).toEqual([
      { name: "orbitDirection", value: "DESCENDING" },
      { name: "operationalMode", value: "IW" },
    ]);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/products/p1/attributes")
    );
  });

  it("fetchProductAttributes throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: "not found" }) })
    );

    await expect(fetchProductAttributes("never-searched")).rejects.toThrow("not found");
  });
});
