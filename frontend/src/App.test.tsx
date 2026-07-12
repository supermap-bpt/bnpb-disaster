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

  it("shows 'Pre Disaster' as a nav dropdown with a 'Landslide' item routing to the renamed Landslide Processing page", () => {
    render(<App />);

    const nav = within(screen.getByRole("navigation"));
    const trigger = nav.getByRole("button", { name: /^pre disaster$/i });
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    fireEvent.click(trigger);
    const landslideLink = screen.getByRole("menuitem", { name: /^landslide$/i });
    expect(landslideLink).toHaveAttribute("href", "/pre-disaster/landslide");

    goTo("/pre-disaster/landslide");
    render(<App />);
    expect(screen.getByRole("heading", { name: /landslide processing/i })).toBeInTheDocument();
  });

  it("Dashboard cards link to the renamed disaster-management routes", () => {
    render(<App />);
    const main = within(screen.getByRole("main"));
    expect(main.getByRole("link", { name: /during disaster/i })).toHaveAttribute(
      "href",
      "/during-disaster"
    );
    expect(main.getByRole("link", { name: /prediction disaster/i })).toHaveAttribute(
      "href",
      "/prediction-disaster"
    );
  });

  it("Dashboard's Pre Disaster card opens the Pre Disaster dropdown directly instead of navigating", () => {
    render(<App />);
    const main = within(screen.getByRole("main"));
    const card = main.getByRole("button", { name: /pre disaster/i });

    fireEvent.pointerDown(card, { button: 0, ctrlKey: false });
    fireEvent.click(card);

    const landslideItem = screen.getByRole("menuitem", { name: /^landslide$/i });
    const floodItem = screen.getByRole("menuitem", { name: /^flood$/i });
    expect(landslideItem).toHaveAttribute("href", "/pre-disaster/landslide");
    expect(floodItem).toHaveAttribute("href", "/pre-disaster/flood");
  });

  it("mounts the activity notifications provider (polls the logs endpoint on load)", async () => {
    render(<App />);
    await waitFor(() => expect(fetchActivityLogs).toHaveBeenCalled());
  });

  it("shows 'Flood' as a second item in the Pre Disaster dropdown, routing to the renamed Flood page", () => {
    render(<App />);

    const nav = within(screen.getByRole("navigation"));
    const trigger = nav.getByRole("button", { name: /^pre disaster$/i });
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    fireEvent.click(trigger);
    const floodLink = screen.getByRole("menuitem", { name: /^flood$/i });
    expect(floodLink).toHaveAttribute("href", "/pre-disaster/flood");

    goTo("/pre-disaster/flood");
    render(<App />);
    expect(screen.getByRole("heading", { name: /deteksi banjir|flood detection/i })).toBeInTheDocument();
  });
});
