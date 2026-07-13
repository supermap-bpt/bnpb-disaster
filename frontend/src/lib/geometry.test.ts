import { describe, expect, it } from "vitest";
import { flattenFootprintPoints } from "./geometry";

describe("flattenFootprintPoints", () => {
  it("returns an empty array for empty coordinates", () => {
    expect(flattenFootprintPoints([])).toEqual([]);
  });

  it("flattens a Polygon's single ring", () => {
    const polygon = [
      [95, 4],
      [98, 4],
      [98, 6],
      [95, 6],
    ];
    expect(flattenFootprintPoints([polygon])).toEqual([
      [95, 4],
      [98, 4],
      [98, 6],
      [95, 6],
    ]);
  });

  it("flattens a MultiPolygon's two rings into one flat point list", () => {
    const ring1 = [
      [180, -83.1],
      [180, -61.6],
      [172.7, -81.7],
    ];
    const ring2 = [
      [-180, -61.6],
      [-180, -83.1],
      [-179.4, -83.2],
    ];
    const multiPolygon = [[ring1], [ring2]];
    expect(flattenFootprintPoints(multiPolygon)).toEqual([...ring1, ...ring2]);
  });
});
