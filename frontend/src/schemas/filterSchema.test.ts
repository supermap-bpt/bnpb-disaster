import { describe, expect, it } from "vitest";
import { filterSchema } from "./filterSchema";

describe("filterSchema", () => {
  it("accepts a valid filter with one product type", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_1_GRD"],
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    expect(result.success).toBe(true);
  });

  it("accepts multiple product types", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_1_SLC", "SENTINEL_1_GRD"],
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    expect(result.success).toBe(true);
  });

  it("rejects an empty product type list", () => {
    const result = filterSchema.safeParse({
      productType: [],
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    expect(result.success).toBe(false);
  });

  it("accepts Sentinel-2 product types", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_2_L1C", "SENTINEL_2_L2A"],
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    expect(result.success).toBe(true);
  });

  it("defaults cloudCoverMax to 100 when omitted", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_1_GRD"],
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.cloudCoverMax).toBe(100);
  });

  it("rejects a cloudCoverMax above 100", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_2_L2A"],
      cloudCoverMax: 150,
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    expect(result.success).toBe(false);
  });

  it("rejects an unknown productType", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_3_FOO"],
      dateFrom: "2026-01-01",
      dateUntil: "2026-02-01",
    });
    expect(result.success).toBe(false);
  });

  it("rejects dateUntil before dateFrom", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_1_SLC"],
      dateFrom: "2026-02-01",
      dateUntil: "2026-01-01",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(["dateUntil"]);
    }
  });

  it("rejects empty dateFrom", () => {
    const result = filterSchema.safeParse({
      productType: ["SENTINEL_1_SLC"],
      dateFrom: "",
      dateUntil: "2026-01-01",
    });
    expect(result.success).toBe(false);
  });

  it("accepts an empty date range when only DEMNAS product types are selected", () => {
    const result = filterSchema.safeParse({
      productType: ["DEMNAS_25K"],
      dateFrom: "",
      dateUntil: "",
    });
    expect(result.success).toBe(true);
  });

  it("still requires a date range when a non-DEMNAS product type is present", () => {
    const result = filterSchema.safeParse({
      productType: ["DEMNAS_25K", "SENTINEL_1_GRD"],
      dateFrom: "",
      dateUntil: "",
    });
    expect(result.success).toBe(false);
  });
});
