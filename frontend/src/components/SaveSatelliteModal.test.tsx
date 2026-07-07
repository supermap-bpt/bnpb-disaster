import { fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "../context/LanguageContext";
import type { SearchResultItem } from "../context/GISContext";
import SaveSatelliteModal from "./SaveSatelliteModal";

vi.mock("../api/client", () => ({
  fetchProductAttributes: vi.fn(),
  saveSatellite: vi.fn(),
}));

import { fetchProductAttributes, saveSatellite } from "../api/client";

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

const SAMPLE_ITEM: SearchResultItem = {
  id: "p1",
  name: "S1A_IW_GRDH_1SDV_20260126.SAFE",
  productType: "SENTINEL_1_GRD",
  sensingTime: "2026-01-26T11:43:01Z",
  size: "1632MB",
  polarisation: "VV&VH",
  footprint: { type: "Polygon", coordinates: [[[95, 4], [98, 4], [98, 6]]] },
};

beforeEach(() => {
  vi.mocked(fetchProductAttributes).mockReset();
  vi.mocked(saveSatellite).mockReset();
});

describe("SaveSatelliteModal", () => {
  it("shows a validation error when submitting a blank name", async () => {
    render(
      <Providers>
        <SaveSatelliteModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    fireEvent.click(screen.getByRole("button", { name: /^simpan$/i }));

    expect(await screen.findByText(/nama satelit wajib diisi/i)).toBeInTheDocument();
    expect(saveSatellite).not.toHaveBeenCalled();
  });

  it("submits the trimmed name plus fetched attributes, shows success on 200", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([{ name: "orbitNumber", value: "57694" }]);
    vi.mocked(saveSatellite).mockResolvedValue({
      success: true,
      message: "Satellite saved successfully.",
      satelliteId: "sat-1",
    });

    render(
      <Providers>
        <SaveSatelliteModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    fireEvent.change(screen.getByLabelText(/nama satelit/i), {
      target: { value: "  Aceh Flood Jan 2025  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /^simpan$/i }));

    await waitFor(() =>
      expect(saveSatellite).toHaveBeenCalledWith(
        "Aceh Flood Jan 2025",
        expect.objectContaining({
          id: "p1",
          mission: "Sentinel-1",
          instrumentName: "SAR",
          attributes: [{ name: "orbitNumber", value: "57694" }],
        })
      )
    );
    expect(await screen.findByText(/satellite saved successfully/i)).toBeInTheDocument();
  });

  it("shows the backend's message inline when success is false (duplicate name)", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([]);
    vi.mocked(saveSatellite).mockResolvedValue({
      success: false,
      message: 'A saved satellite named "Dup" already exists.',
      satelliteId: null,
    });

    render(
      <Providers>
        <SaveSatelliteModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    fireEvent.change(screen.getByLabelText(/nama satelit/i), { target: { value: "Dup" } });
    fireEvent.click(screen.getByRole("button", { name: /^simpan$/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });

  it("disables Save and Cancel while saving is in flight", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([]);
    let resolveSave!: (value: import("../api/client").SaveSatelliteResponse) => void;
    vi.mocked(saveSatellite).mockReturnValue(
      new Promise((resolve) => {
        resolveSave = resolve;
      })
    );

    render(
      <Providers>
        <SaveSatelliteModal item={SAMPLE_ITEM} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    fireEvent.change(screen.getByLabelText(/nama satelit/i), { target: { value: "In Flight" } });
    fireEvent.click(screen.getByRole("button", { name: /^simpan$/i }));

    expect(await screen.findByRole("button", { name: /menyimpan/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^batal$/i })).toBeDisabled();

    await act(async () => {
      resolveSave({ success: true, message: "ok", satelliteId: "sat-2" });
    });
  });

  it("saves a Sentinel-2 item with mission Sentinel-2 and instrument MSI", async () => {
    vi.mocked(fetchProductAttributes).mockResolvedValue([]);
    vi.mocked(saveSatellite).mockResolvedValue({
      success: true,
      message: "Satellite saved successfully.",
      satelliteId: "sat-2",
    });

    const s2Item = { ...SAMPLE_ITEM, id: "p2", productType: "SENTINEL_2_L2A" as const };

    render(
      <Providers>
        <SaveSatelliteModal item={s2Item} open={true} onOpenChange={() => {}} />
      </Providers>
    );

    fireEvent.change(screen.getByLabelText(/nama satelit/i), { target: { value: "Banjir Aceh" } });
    fireEvent.click(screen.getByRole("button", { name: /^simpan$/i }));

    await waitFor(() =>
      expect(saveSatellite).toHaveBeenCalledWith(
        "Banjir Aceh",
        expect.objectContaining({ id: "p2", mission: "Sentinel-2", instrumentName: "MSI" })
      )
    );
  });
});
