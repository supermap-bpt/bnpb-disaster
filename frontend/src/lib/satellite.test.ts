import { describe, expect, it } from "vitest";
import { getDemnasLoginDownloadUrl, getDemnasPreviewImageUrl } from "./satellite";

describe("getDemnasPreviewImageUrl", () => {
  it("builds BIG's public per-tile preview image URL from the tile id", () => {
    expect(getDemnasPreviewImageUrl("1118-631")).toBe(
      "https://tanahair.indonesia.go.id/demnas/images/DEMNAS_1118-631.jpg"
    );
  });
});

describe("getDemnasLoginDownloadUrl", () => {
  it("builds BIG's login deep-link with page and filename params", () => {
    expect(getDemnasLoginDownloadUrl("1118-631")).toBe(
      "https://tanahair.indonesia.go.id/portal-web/login?page=/unduh/demnas&filename=DEMNAS_1118-631_v1.0.tif"
    );
  });
});
