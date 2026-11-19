import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom does no layout and has no ResizeObserver, so the chart draws at its minimum width.
Object.defineProperty(globalThis, "ResizeObserver", {
  configurable: true,
  value: class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
});

afterEach(cleanup);
