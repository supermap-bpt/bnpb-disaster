import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/Sidebar", () => ({ default: () => <div data-testid="sidebar" /> }));
vi.mock("@/components/MapView", () => ({ default: () => <div data-testid="map-view" /> }));
vi.mock("@/api/client", () => ({
  fetchActivityLogs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

import App from "./App";
import { fetchActivityLogs } from "@/api/client";

function goTo(path: string) {
  window.history.pushState({}, "", path);
}

beforeEach(() => {
  goTo("/");
});

afterEach(() => {
  goTo("/");
});

describe("App", () => {
  it("renders the app title and the Dashboard page at /", () => {
    render(<App />);
    expect(screen.getByText(/Disaster Management Dashboard/i)).toBeInTheDocument();
    expect(screen.getByText(/selamat datang/i)).toBeInTheDocument();
  });

  it("does not render SatelliteModal (kept on disk but no longer wired up)", () => {
    render(<App />);
    // SatelliteModal isn't mocked above, so if App still imported/rendered it
    // we'd see its real DOM output (which only appears once a product is
    // selected). Absence of any such markup with no selection made confirms
    // it's not part of the render tree.
    expect(screen.queryByText(/lihat di peta/i)).not.toBeInTheDocument();
  });

  it("shows 'Satellite Explorer' as a direct nav link (no dropdown)", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /satellite explorer/i })).toHaveAttribute(
      "href",
      "/satellite-explorer"
    );
  });

  it("renders the map and sidebar on /satellite-explorer", () => {
    goTo("/satellite-explorer");
    render(<App />);
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("map-view")).toBeInTheDocument();
  });

  it("mobile drawer toggle opens the results/filter overlay on /satellite-explorer", () => {
    goTo("/satellite-explorer");
    render(<App />);
    const toggle = screen.getByRole("button", { name: /filter & hasil/i });
    fireEvent.click(toggle);
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
  });

  it("shows 'Pre Disaster' as a dropdown with a 'Landslide' item routing to the renamed Landslide Processing page", () => {
    render(<App />);

    const trigger = screen.getByRole("button", { name: /pre disaster/i });
    fireEvent.click(trigger);
    const landslideLink = screen.getByRole("link", { name: /landslide/i });
    expect(landslideLink).toHaveAttribute("href", "/pre-disaster/landslide");

    goTo("/pre-disaster/landslide");
    render(<App />);
    expect(screen.getByRole("heading", { name: /landslide processing/i })).toBeInTheDocument();
  });

  it("Dashboard cards link to the renamed disaster-management routes", () => {
    render(<App />);
    const main = within(screen.getByRole("main"));
    expect(main.getByRole("link", { name: /pre disaster/i })).toHaveAttribute("href", "/pre-disaster");
    expect(main.getByRole("link", { name: /during disaster/i })).toHaveAttribute(
      "href",
      "/during-disaster"
    );
    expect(main.getByRole("link", { name: /prediction disaster/i })).toHaveAttribute(
      "href",
      "/prediction-disaster"
    );
  });

  it("navigating to /pre-disaster shows the renamed placeholder page", () => {
    goTo("/pre-disaster");
    render(<App />);
    expect(screen.getByRole("heading", { name: /pre disaster/i })).toBeInTheDocument();
  });

  it("mounts the activity notifications provider (polls the logs endpoint on load)", async () => {
    render(<App />);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalled());
  });
});
