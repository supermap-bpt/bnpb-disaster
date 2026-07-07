import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GISProvider, useGIS } from "./GISContext";

function Probe() {
  const gis = useGIS();
  return (
    <div>
      <span data-testid="search-count">{gis.searchResults.length}</span>
      <span data-testid="selected">{gis.selectedProductId ?? "none"}</span>
      <button
        onClick={() =>
          gis.setSearchResults(
            [
              {
                id: "p1",
                name: "p1.SAFE",
                productType: "SENTINEL_1_GRD",
                sensingTime: "2026-01-26T11:43:01Z",
                size: "1632MB",
                polarisation: "VV&VH",
                footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6]]] },
              },
            ],
            1
          )
        }
      >
        load
      </button>
      <button onClick={() => gis.selectProduct("p1")}>select</button>
    </div>
  );
}

describe("GISContext", () => {
  it("starts empty and updates via actions", () => {
    render(
      <GISProvider>
        <Probe />
      </GISProvider>
    );

    expect(screen.getByTestId("search-count").textContent).toBe("0");
    expect(screen.getByTestId("selected").textContent).toBe("none");

    act(() => screen.getByText("load").click());
    expect(screen.getByTestId("search-count").textContent).toBe("1");

    act(() => screen.getByText("select").click());
    expect(screen.getByTestId("selected").textContent).toBe("p1");
  });

  it("starts with no AOI, then stores the placeRing set by a geocoded search", () => {
    function AoiProbe() {
      const gis = useGIS();
      return (
        <div>
          <span data-testid="place">{gis.placeRing ? gis.placeRing.length : "none"}</span>
          <button
            onClick={() =>
              gis.setPlaceRing([
                [96.0, 5.0],
                [97.0, 5.0],
                [97.0, 5.5],
              ])
            }
          >
            set-place
          </button>
        </div>
      );
    }
    render(
      <GISProvider>
        <AoiProbe />
      </GISProvider>
    );

    expect(screen.getByTestId("place").textContent).toBe("none");
    act(() => screen.getByText("set-place").click());
    expect(screen.getByTestId("place").textContent).toBe("3");
  });

  it("tracks addressQuery, and resetAll clears it back to empty", () => {
    function AddressProbe() {
      const gis = useGIS();
      return (
        <div>
          <span data-testid="address">{gis.addressQuery || "empty"}</span>
          <button onClick={() => gis.setAddressQuery("Aceh Tamiang")}>type</button>
          <button onClick={() => gis.resetAll()}>reset</button>
        </div>
      );
    }
    render(
      <GISProvider>
        <AddressProbe />
      </GISProvider>
    );

    expect(screen.getByTestId("address").textContent).toBe("empty");
    act(() => screen.getByText("type").click());
    expect(screen.getByTestId("address").textContent).toBe("Aceh Tamiang");
    act(() => screen.getByText("reset").click());
    expect(screen.getByTestId("address").textContent).toBe("empty");
  });

  it("appendSearchResults concatenates rather than replaces, for Load More", () => {
    function AppendProbe() {
      const gis = useGIS();
      const item = (id: string) => ({
        id,
        name: `${id}.SAFE`,
        productType: "SENTINEL_1_GRD" as const,
        sensingTime: "2026-01-26T11:43:01Z",
        size: "1632MB",
        polarisation: "VV&VH",
        footprint: { type: "Polygon", coordinates: [] },
      });
      return (
        <div>
          <span data-testid="count">{gis.searchResults.length}</span>
          <button onClick={() => gis.setSearchResults([item("p1")], 2)}>page1</button>
          <button onClick={() => gis.appendSearchResults([item("p2")], 2)}>page2</button>
        </div>
      );
    }
    render(
      <GISProvider>
        <AppendProbe />
      </GISProvider>
    );

    act(() => screen.getByText("page1").click());
    expect(screen.getByTestId("count").textContent).toBe("1");
    act(() => screen.getByText("page2").click());
    expect(screen.getByTestId("count").textContent).toBe("2");
  });

  it("throws when useGIS is used outside GISProvider", () => {
    function Bare() {
      useGIS();
      return null;
    }
    expect(() => render(<Bare />)).toThrow(/useGIS must be used within a GISProvider/);
  });
});
