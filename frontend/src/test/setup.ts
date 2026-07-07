import "@testing-library/jest-dom/vitest";

// Radix UI primitives (Popover/DropdownMenu use Popper positioning, which
// needs ResizeObserver - jsdom doesn't implement it.
if (!("ResizeObserver" in window)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  // @ts-expect-error jsdom has no ResizeObserver
  window.ResizeObserver = ResizeObserverStub;
}

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom has no PointerEvent constructor. Radix UI's DropdownMenu/Menu
// triggers open exclusively on "pointerdown" (not "click"), so tests need a
// real PointerEvent for `fireEvent.pointerDown` to carry properties like
// `button`/`ctrlKey` correctly.
if (!("PointerEvent" in window)) {
  class PointerEventPolyfill extends MouseEvent {
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
    }
  }
  // @ts-expect-error jsdom has no PointerEvent
  window.PointerEvent = PointerEventPolyfill;
}
