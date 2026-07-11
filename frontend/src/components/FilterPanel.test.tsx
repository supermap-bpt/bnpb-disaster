import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEffect, type ReactNode } from "react";
import { GISProvider, useGIS, INDONESIA_BBOX, type AoiRing } from "../context/GISContext";
import { LanguageProvider } from "../context/LanguageContext";
import FilterPanel from "./FilterPanel";

function Providers({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <GISProvider>{children}</GISProvider>
    </LanguageProvider>
  );
}

vi.mock("../api/client", () => ({
  fetchSearch: vi.fn(),
}));

import { fetchSearch } from "../api/client";

const SAMPLE_PLACE: AoiRing = [
  [96.0, 5.0],
  [97.0, 5.0],
  [97.0, 5.5],
];

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Opens the Dari/Sampai date Popover, jumps the Calendar's month/year
 * dropdowns to the target date, clicks the day, then the popover auto-closes. */
function pickDate(triggerLabel: RegExp, year: number, month: number, day: number) {
  fireEvent.click(screen.getByLabelText(triggerLabel));
  fireEvent.change(screen.getByLabelText("Choose the Year"), {
    target: { value: String(year) },
  });
  fireEvent.change(screen.getByLabelText("Choose the Month"), {
    target: { value: String(month) },
  });
  fireEvent.click(
    screen.getByRole("button", {
      name: new RegExp(`${MONTH_NAMES[month]} ${day}(?!\\d)\\w*, ${year}`, "i"),
    })
  );
}

function WithPlace({ ring, children }: { ring: AoiRing | null; children: ReactNode }) {
  const gis = useGIS();
  useEffect(() => {
    gis.setPlaceRing(ring);
  }, [ring]);
  return <>{children}</>;
}

function WithAddressQuery({ query, children }: { query: string; children: ReactNode }) {
  const gis = useGIS();
  useEffect(() => {
    gis.setAddressQuery(query);
  }, [query]);
  return <>{children}</>;
}

function ResultsProbe() {
  const gis = useGIS();
  return <span data-testid="result-count">{gis.searchResults.length}</span>;
}

/** All tree groups start collapsed; expand the named group's chevron
 * (aria-label "Expand <name>") before a test needs to see/click its leaves. */
function expandGroup(name: RegExp) {
  fireEvent.click(screen.getByRole("button", { name }));
}

beforeEach(() => {
  vi.mocked(fetchSearch).mockReset();
});

describe("FilterPanel", () => {
  it("defaults to nothing checked, and submits filter + placeRing + skip=0 once a leaf is picked", async () => {
    vi.mocked(fetchSearch).mockResolvedValue({
      results: [
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
      total: 1,
    });

    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <WithAddressQuery query="Somewhere, Indonesia">
            <FilterPanel />
            <ResultsProbe />
          </WithAddressQuery>
        </WithPlace>
      </Providers>
    );

    expect(screen.getByLabelText(/^sentinel-1$/i)).toHaveAttribute("data-state", "unchecked");

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    expect(screen.getByLabelText(/level 1-grd/i)).not.toBeChecked();
    expect(screen.getByLabelText(/level 1-slc/i)).not.toBeChecked();

    fireEvent.click(screen.getByLabelText(/level 1-grd/i));
    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    await waitFor(() => expect(screen.getByTestId("result-count").textContent).toBe("1"));
    expect(fetchSearch).toHaveBeenCalledWith(
      { productType: ["SENTINEL_1_GRD"], cloudCoverMax: 100, dateFrom: "2026-01-01", dateUntil: "2026-02-01" },
      SAMPLE_PLACE,
      0
    );
  });

  it("submits both product types when both checkboxes are checked", async () => {
    vi.mocked(fetchSearch).mockResolvedValue({ results: [], total: 0 });

    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <WithAddressQuery query="Somewhere, Indonesia">
            <FilterPanel />
          </WithAddressQuery>
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/level 1-slc/i));
    fireEvent.click(screen.getByLabelText(/level 1-grd/i));
    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    await waitFor(() => expect(fetchSearch).toHaveBeenCalled());
    expect(fetchSearch).toHaveBeenCalledWith(
      { productType: ["SENTINEL_1_SLC", "SENTINEL_1_GRD"], cloudCoverMax: 100, dateFrom: "2026-01-01", dateUntil: "2026-02-01" },
      SAMPLE_PLACE,
      0
    );
  });

  it("checking Sentinel-1 checks both C-SAR leaves; unchecking clears both", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expect(screen.getByLabelText(/^sentinel-1$/i)).toHaveAttribute("data-state", "unchecked");

    expandGroup(/expand sentinel-1/i);
    expect(screen.getByLabelText(/^c-sar$/i)).toHaveAttribute("data-state", "unchecked");
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/^sentinel-1$/i));
    expect(screen.getByLabelText(/level 1-slc/i)).toBeChecked();
    expect(screen.getByLabelText(/level 1-grd/i)).toBeChecked();
    expect(screen.getByLabelText(/^sentinel-1$/i)).toHaveAttribute("data-state", "checked");
    expect(screen.getByLabelText(/^c-sar$/i)).toHaveAttribute("data-state", "checked");

    fireEvent.click(screen.getByLabelText(/^sentinel-1$/i));
    expect(screen.getByLabelText(/level 1-slc/i)).not.toBeChecked();
    expect(screen.getByLabelText(/level 1-grd/i)).not.toBeChecked();
  });

  it("checking C-SAR checks both leaves", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/level 1-grd/i));
    fireEvent.click(screen.getByLabelText(/^c-sar$/i));
    expect(screen.getByLabelText(/level 1-slc/i)).toBeChecked();
    expect(screen.getByLabelText(/level 1-grd/i)).toBeChecked();
  });

  it("groups start collapsed; expanding Sentinel-1 then C-SAR reveals its leaves", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expect(screen.queryByLabelText(/level 1-slc/i)).not.toBeInTheDocument();
    expandGroup(/expand sentinel-1/i);
    expect(screen.queryByLabelText(/level 1-slc/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /expand c-sar/i }));
    expect(screen.getByLabelText(/level 1-slc/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /collapse c-sar/i }));
    expect(screen.queryByLabelText(/level 1-slc/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /expand c-sar/i }));
    expect(screen.getByLabelText(/level 1-slc/i)).toBeInTheDocument();
  });

  it("checking Sentinel-2 checks both MSI leaves without touching Sentinel-1", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-2/i);
    expandGroup(/expand msi/i);
    fireEvent.click(screen.getByLabelText(/^sentinel-2$/i));
    expect(screen.getByLabelText(/^l1c$/i)).toBeChecked();
    expect(screen.getByLabelText(/^l2a$/i)).toBeChecked();
    // Default S1 state (nothing checked) must be untouched.
    expect(screen.getByLabelText(/^sentinel-1$/i)).toHaveAttribute("data-state", "unchecked");
  });

  it("checking Sentinel-3 checks both SLSTR leaves without touching Sentinel-1 or Sentinel-2", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-3/i);
    expandGroup(/expand slstr/i);
    fireEvent.click(screen.getByLabelText(/^sentinel-3$/i));
    expect(screen.getByLabelText(/level-2 lst/i)).toBeChecked();
    expect(screen.getByLabelText(/level-2 wst/i)).toBeChecked();
    // Default S1/S2 state (nothing checked) must be untouched.
    expect(screen.getByLabelText(/^sentinel-1$/i)).toHaveAttribute("data-state", "unchecked");
    expect(screen.getByLabelText(/^sentinel-2$/i)).toHaveAttribute("data-state", "unchecked");
  });

  it("submits Sentinel-3 product types when their checkboxes are checked", async () => {
    vi.mocked(fetchSearch).mockResolvedValue({ results: [], total: 0 });

    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <WithAddressQuery query="Somewhere, Indonesia">
            <FilterPanel />
          </WithAddressQuery>
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-3/i);
    expandGroup(/expand slstr/i);
    fireEvent.click(screen.getByLabelText(/level-2 lst/i));
    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    await waitFor(() => expect(fetchSearch).toHaveBeenCalled());
    expect(fetchSearch).toHaveBeenCalledWith(
      {
        productType: ["SENTINEL_3_SLSTR_L2_LST"],
        cloudCoverMax: 100,
        dateFrom: "2026-01-01",
        dateUntil: "2026-02-01",
      },
      SAMPLE_PLACE,
      0
    );
  });

  it("checking a DEMNAS leaf clears any checked Sentinel leaves", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/level 1-grd/i));
    expect(screen.getByLabelText(/level 1-grd/i)).toBeChecked();

    expandGroup(/expand demnas/i);
    expandGroup(/expand skala/i);
    fireEvent.click(screen.getByLabelText(/^25k$/i));

    expect(screen.getByLabelText(/^25k$/i)).toBeChecked();
    expect(screen.getByLabelText(/level 1-grd/i)).not.toBeChecked();
  });

  it("checking a Sentinel leaf clears any checked DEMNAS leaves", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand demnas/i);
    expandGroup(/expand skala/i);
    fireEvent.click(screen.getByLabelText(/^25k$/i));
    expect(screen.getByLabelText(/^25k$/i)).toBeChecked();

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/level 1-grd/i));

    expect(screen.getByLabelText(/level 1-grd/i)).toBeChecked();
    expect(screen.getByLabelText(/^25k$/i)).not.toBeChecked();
  });

  it("checking the DEMNAS group checks both Skala leaves and clears Sentinel selections", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/level 1-grd/i));

    expandGroup(/expand demnas/i);
    expandGroup(/expand skala/i);
    fireEvent.click(screen.getByLabelText(/^demnas$/i));

    expect(screen.getByLabelText(/^25k$/i)).toBeChecked();
    expect(screen.getByLabelText(/^50k$/i)).toBeChecked();
    expect(screen.getByLabelText(/level 1-grd/i)).not.toBeChecked();
  });

  it("submits DEMNAS product types when their checkboxes are checked", async () => {
    vi.mocked(fetchSearch).mockResolvedValue({ results: [], total: 0 });

    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <WithAddressQuery query="Somewhere, Indonesia">
            <FilterPanel />
          </WithAddressQuery>
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand demnas/i);
    expandGroup(/expand skala/i);
    fireEvent.click(screen.getByLabelText(/^25k$/i));
    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    await waitFor(() => expect(fetchSearch).toHaveBeenCalled());
    expect(fetchSearch).toHaveBeenCalledWith(
      {
        productType: ["DEMNAS_25K"],
        cloudCoverMax: 100,
        dateFrom: "2026-01-01",
        dateUntil: "2026-02-01",
      },
      SAMPLE_PLACE,
      0
    );
  });

  it("cloud cover slider is disabled until a Sentinel-2 leaf is checked", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-2/i);
    expandGroup(/expand msi/i);
    expect(screen.getByRole("slider")).toHaveAttribute("data-disabled");
    fireEvent.click(screen.getByLabelText(/^l2a$/i));
    expect(screen.getByRole("slider")).not.toHaveAttribute("data-disabled");
  });

  it("submits cloudCoverMax along with the selected product types", async () => {
    vi.mocked(fetchSearch).mockResolvedValue({ results: [], total: 0 });

    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <WithAddressQuery query="Somewhere, Indonesia">
            <FilterPanel />
          </WithAddressQuery>
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-2/i);
    expandGroup(/expand msi/i);
    fireEvent.click(screen.getByLabelText(/^l2a$/i));
    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    await waitFor(() => expect(fetchSearch).toHaveBeenCalled());
    expect(fetchSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        cloudCoverMax: 100,
        productType: expect.arrayContaining(["SENTINEL_2_L2A"]),
      }),
      SAMPLE_PLACE,
      0
    );
  });

  it("shows a validation error and does not search when no data source is checked", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    expect(await screen.findByText(/pilih minimal satu/i)).toBeInTheDocument();
    expect(fetchSearch).not.toHaveBeenCalled();
  });

  it("shows a validation error and does not call fetchSearch when dateUntil is before dateFrom", async () => {
    render(
      <Providers>
        <WithPlace ring={SAMPLE_PLACE}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    pickDate(/^dari$/i, 2026, 1, 1);
    pickDate(/^sampai$/i, 2026, 0, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    expect(await screen.findByText(/tidak boleh mendahului/i)).toBeInTheDocument();
    expect(fetchSearch).not.toHaveBeenCalled();
  });

  it("uses the Indonesia bounding box when the address is empty and no place is selected", async () => {
    vi.mocked(fetchSearch).mockResolvedValue({ results: [], total: 0 });

    render(
      <Providers>
        <WithPlace ring={null}>
          <FilterPanel />
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/level 1-grd/i));
    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    await waitFor(() => expect(fetchSearch).toHaveBeenCalled());
    expect(fetchSearch).toHaveBeenCalledWith(expect.anything(), INDONESIA_BBOX, 0);
    expect(screen.queryByText(/cari & pilih lokasi/i)).not.toBeInTheDocument();
  });

  it("still blocks submit when the address has text but no place has been selected yet", async () => {
    render(
      <Providers>
        <WithPlace ring={null}>
          <WithAddressQuery query="Aceh Tam">
            <FilterPanel />
          </WithAddressQuery>
        </WithPlace>
      </Providers>
    );

    expandGroup(/expand sentinel-1/i);
    expandGroup(/expand c-sar/i);
    fireEvent.click(screen.getByLabelText(/level 1-grd/i));
    pickDate(/^dari$/i, 2026, 0, 1);
    pickDate(/^sampai$/i, 2026, 1, 1);
    fireEvent.click(screen.getByRole("button", { name: /^cari$/i }));

    expect(await screen.findByText(/cari & pilih lokasi/i)).toBeInTheDocument();
    expect(fetchSearch).not.toHaveBeenCalled();
  });

});
