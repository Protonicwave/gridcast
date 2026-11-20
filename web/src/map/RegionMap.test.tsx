import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { rampColour } from "../chartGeometry";
import type { Outlook } from "../forecastApi";
import { RegionMap } from "./RegionMap";
import shapes from "./regionShapes.json";

/** 15:10 on Thursday 19 November 2026, UK time. */
const NOW_MS = Date.parse("2026-11-19T15:10Z");
const FIRST_SLOT_MS = Date.parse("2026-11-19T15:00Z");
const SLOT_COUNT = 96;
const NAMES = ["North Scotland", "South Scotland", "North West England", "North East England", "Yorkshire", "North Wales", "South Wales", "West Midlands", "East Midlands", "East England", "South West England", "South England", "London", "South East England"];

/** Region n holds n times ten g per kWh until half hour 4, then n times ten plus 100. */
function outlooks(): ReadonlyMap<number, Outlook> {
  return new Map(
    NAMES.map((regionName, index) => {
      const regionId = index + 1;
      const intensities = Array.from({ length: SLOT_COUNT }, (_, slot) => regionId * 10 + (slot < 4 ? 0 : 100));
      const windows = new Map();
      return [regionId, { regionId, regionName, fetchedAtMs: NOW_MS, firstSlotStartMs: FIRST_SLOT_MS, slotMs: 1_800_000, intensities, windows }] as const;
    }),
  );
}

function renderMap(overrides: Partial<Parameters<typeof RegionMap>[0]> = {}) {
  const onSelect = vi.fn<(regionId: number) => void>();
  render(<RegionMap outlooks={outlooks()} cursor={0} selectedId={null} nowMs={NOW_MS} onSelect={onSelect} {...overrides} />);
  return onSelect;
}

function paths(): SVGPathElement[] {
  return [...document.querySelectorAll<SVGPathElement>("path.region")];
}

/** Gives every measured element a 400 by 640 px box, so the map has a drawn size to place labels against. */
function measureMapAs400By640() {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ width: 400, height: 640 } as DOMRect);
}

it("draws a shape for each of the 14 regions", () => {
  renderMap();
  expect(paths()).toHaveLength(14);
  expect(paths().map((path) => path.getAttribute("d"))).toEqual(Object.values(shapes.regions).map((shape) => shape.path));
});

it("colours each region by its forecast at the cursor's half hour", () => {
  renderMap({ cursor: 0 });
  expect(paths().map((path) => path.getAttribute("fill"))).toEqual(NAMES.map((_, index) => rampColour((index + 1) * 10)));
});

it("recolours every region when the cursor moves", () => {
  renderMap({ cursor: 10 });
  expect(paths().map((path) => path.getAttribute("fill"))).toEqual(NAMES.map((_, index) => rampColour((index + 1) * 10 + 100)));
});

it("holds the last half hour when the cursor is past the end", () => {
  renderMap({ cursor: 500 });
  expect(paths()[0]?.getAttribute("fill")).toBe(rampColour(110));
});

it("names the half hour in its heading", () => {
  renderMap({ cursor: 0 });
  expect(screen.getByRole("heading", { name: "Across Great Britain, now" })).toBeTruthy();
});

it("names a later half hour by its day and time", () => {
  renderMap({ cursor: 18 });
  expect(screen.getByRole("heading", { name: "Across Great Britain, tonight 00:00" })).toBeTruthy();
});

it("gives each shape a title with the region and its value", () => {
  renderMap({ cursor: 0 });
  expect(paths()[12]?.querySelector("title")?.textContent).toBe("London, 130 g");
});

it("marks the selected region", () => {
  renderMap({ selectedId: 5 });
  expect(paths().filter((path) => path.classList.contains("region--selected"))).toEqual([paths()[4]]);
});

it("marks no region before one is chosen", () => {
  renderMap({ selectedId: null });
  expect(document.querySelectorAll(".region--selected")).toHaveLength(0);
});

it("selects the region that was clicked", () => {
  const onSelect = renderMap();
  fireEvent.click(paths()[6] as SVGPathElement);
  expect(onSelect).toHaveBeenCalledExactlyOnceWith(7);
});

it("draws the Shetland inset frame", () => {
  renderMap();
  const frame = document.querySelector("rect.inset-frame");
  expect(frame?.getAttribute("width")).toBe(String(shapes.shetlandFrame.width));
});

it("labels the selected, cleanest and dirtiest regions with their values once the map has a size", () => {
  measureMapAs400By640();
  renderMap({ selectedId: 5 });
  const labels = [...document.querySelectorAll("svg text")].map((text) => text.textContent);
  expect(labels).toEqual(["Yorkshire 50 g", "North Scotland 10 g", "South East England 140 g"]);
});

it("keeps every label inside the map", () => {
  measureMapAs400By640();
  renderMap({ selectedId: 13 });
  for (const text of document.querySelectorAll("svg text")) {
    const x = Number(text.getAttribute("x"));
    const y = Number(text.getAttribute("y"));
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x).toBeLessThanOrEqual(shapes.viewBox.width);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(y).toBeLessThanOrEqual(shapes.viewBox.height);
  }
});

it("draws no labels before the map has been measured", () => {
  renderMap({ selectedId: 5 });
  expect(document.querySelectorAll("svg text")).toHaveLength(0);
});

it("explains the colours in a legend hidden from screen readers", () => {
  renderMap();
  const legend = document.querySelector(".legend");
  expect(legend?.getAttribute("aria-hidden")).toBe("true");
  expect(legend?.textContent).toContain("300+ g CO2 per kWh");
});
