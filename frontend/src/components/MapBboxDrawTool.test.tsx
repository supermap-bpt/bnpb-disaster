import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { LanguageProvider } from "@/context/LanguageContext";
import MapBboxDrawTool from "./MapBboxDrawTool";

type LatLng = { lat: number; lng: number };
let mapEventHandlers: Record<string, (event: { latlng: LatLng }) => void> = {};
const dragDisableMock = vi.fn();
const dragEnableMock = vi.fn();
const rectangleLog: unknown[] = [];
const markerLog: { position: [number, number]; drag: (event: { target: { getLatLng: () => LatLng } }) => void }[] = [];

const mapInstanceMock = {
  dragging: { enable: dragEnableMock, disable: dragDisableMock },
};

vi.mock("react-leaflet", () => ({
  useMap: () => mapInstanceMock,
  useMapEvents: (handlers: Record<string, (event: { latlng: LatLng }) => void>) => {
    mapEventHandlers = handlers;
    return mapInstanceMock;
  },
  Rectangle: (props: { bounds: unknown }) => {
    rectangleLog.push(props.bounds);
    return <div data-testid="rectangle" />;
  },
  Marker: (props: { position: [number, number]; eventHandlers?: { drag?: (event: any) => void } }) => {
    markerLog.push({ position: props.position, drag: props.eventHandlers?.drag as any });
    return <div data-testid="marker" />;
  },
}));

function Providers({ children }: { children: ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}

function latlng(lat: number, lng: number): LatLng {
  return { lat, lng };
}

beforeEach(() => {
  mapEventHandlers = {};
  dragDisableMock.mockReset();
  dragEnableMock.mockReset();
  rectangleLog.length = 0;
  markerLog.length = 0;
});

describe("MapBboxDrawTool", () => {
  it("renders no rectangle/handles when there is no bbox", () => {
    render(
      <Providers>
        <MapBboxDrawTool bbox={null} onBboxChange={vi.fn()} />
      </Providers>
    );

    expect(screen.queryByTestId("rectangle")).not.toBeInTheDocument();
    expect(screen.queryByTestId("marker")).not.toBeInTheDocument();
  });

  it("click-drag draws a rectangle and reports its bbox on mouseup", () => {
    const onBboxChange = vi.fn();
    render(
      <Providers>
        <MapBboxDrawTool bbox={null} onBboxChange={onBboxChange} />
      </Providers>
    );

    fireEvent.click(screen.getByTestId("bbox-draw-button"));
    expect(onBboxChange).toHaveBeenCalledWith(null);

    mapEventHandlers.mousedown({ latlng: latlng(4.0, 97.5) });
    expect(dragDisableMock).toHaveBeenCalled();
    mapEventHandlers.mousemove({ latlng: latlng(5.0, 98.3) });
    expect(rectangleLog[rectangleLog.length - 1]).toEqual([latlng(4.0, 97.5), latlng(5.0, 98.3)]);
    mapEventHandlers.mouseup({ latlng: latlng(5.0, 98.3) });

    expect(dragEnableMock).toHaveBeenCalled();
    expect(onBboxChange).toHaveBeenLastCalledWith([97.5, 4.0, 98.3, 5.0]);
  });

  it("a zero-area click (no drag) does not set a bbox", () => {
    const onBboxChange = vi.fn();
    render(
      <Providers>
        <MapBboxDrawTool bbox={null} onBboxChange={onBboxChange} />
      </Providers>
    );

    fireEvent.click(screen.getByTestId("bbox-draw-button"));
    onBboxChange.mockClear();

    mapEventHandlers.mousedown({ latlng: latlng(4.0, 97.5) });
    mapEventHandlers.mouseup({ latlng: latlng(4.0, 97.5) });

    expect(onBboxChange).not.toHaveBeenCalled();
  });

  it("shows the current bbox readout, with 4 corner handles, and the clear button removes it", () => {
    const onBboxChange = vi.fn();
    render(
      <Providers>
        <MapBboxDrawTool bbox={[97.5, 4.0, 98.3, 5.0]} onBboxChange={onBboxChange} />
      </Providers>
    );

    expect(screen.getByText("97.50, 4.00 → 98.30, 5.00")).toBeInTheDocument();
    expect(screen.getAllByTestId("marker")).toHaveLength(4);

    fireEvent.click(screen.getByTestId("bbox-clear-button"));

    expect(onBboxChange).toHaveBeenCalledWith(null);
  });

  it("dragging the NW corner handle resizes the bbox, anchored on the opposite (SE) corner", () => {
    const onBboxChange = vi.fn();
    render(
      <Providers>
        <MapBboxDrawTool bbox={[97.5, 4.0, 98.3, 5.0]} onBboxChange={onBboxChange} />
      </Providers>
    );

    // Render order in MapBboxDrawTool.tsx's JSX is nw, ne, sw, se.
    const nwDrag = markerLog[0].drag;
    nwDrag({ target: { getLatLng: () => latlng(5.5, 97.2) } });

    expect(onBboxChange).toHaveBeenCalledWith([97.2, 4.0, 98.3, 5.5]);
  });

  it("dragging a corner past its opposite corner is clamped (never inverts the bbox)", () => {
    const onBboxChange = vi.fn();
    render(
      <Providers>
        <MapBboxDrawTool bbox={[97.5, 4.0, 98.3, 5.0]} onBboxChange={onBboxChange} />
      </Providers>
    );

    const nwDrag = markerLog[0].drag;
    // Dragging NW's longitude past the SE corner's maxLon (98.3) would invert minLon >= maxLon.
    nwDrag({ target: { getLatLng: () => latlng(5.5, 99.0) } });

    expect(onBboxChange).not.toHaveBeenCalled();
  });
});
