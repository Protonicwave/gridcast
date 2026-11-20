import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import shapes from "./regionShapes.json";

vi.mock("./RegionMap", () => {
  throw new Error("the chunk could not be fetched");
});

it("says the map did not load and draws nothing else in its place", async () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { MapSlot } = await import("./MapSlot");
  render(<MapSlot outlooks={new Map()} cursor={0} selectedId={null} nowMs={0} onSelect={() => undefined} />);
  expect((await screen.findByRole("status")).textContent).toContain("The map did not load.");
  expect(document.querySelectorAll("svg")).toHaveLength(0);
});

it("holds the map's shape while it loads", async () => {
  const { MAP_ASPECT_RATIO } = await import("./MapSlot");
  expect(MAP_ASPECT_RATIO).toBeCloseTo(shapes.viewBox.width / shapes.viewBox.height, 3);
});
