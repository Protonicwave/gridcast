import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AccuracyView } from "./AccuracyView";

const EDGES = [
  [1, 6],
  [6, 12],
  [12, 24],
  [24, 48],
] as const;

type Body = Record<string, unknown>;

function accuracyBody(overrides: Body = {}): Body {
  return {
    until: "2026-11-28",
    bands: EDGES.map(([fromHours, toHours], index) => ({
      fromHours,
      toHours,
      pairs: 9000,
      maeGPerKwh: 8 + index,
      interval: { low: 7.5 + index, high: 8.5 + index },
    })),
    difference: { maeGPerKwh: 3, interval: { low: 1.25, high: 4.5 } },
    days: { usable: ["2026-11-21", "2026-11-22"], excluded: [{ day: "2026-11-20", reason: "only 40 of 48 actuals stored" }] },
    ...overrides,
  };
}

function serve(body: unknown, status = 200) {
  const fake = vi.fn<typeof fetch>(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
  vi.stubGlobal("fetch", fake);
  return fake;
}

function renderView() {
  return render(<AccuracyView apiBaseUrl="" />);
}

it("shows each band's error with its interval, and Gridcast's row as to come", async () => {
  serve(accuracyBody());
  renderView();
  const table = await screen.findByRole("table", { name: /forecast error by horizon/i });
  const neso = within(table).getByRole("row", { name: /^NESO/ });
  expect(within(neso).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["8.0 g7.5 to 8.5", "9.0 g8.5 to 9.5", "10.0 g9.5 to 10.5", "11.0 g10.5 to 11.5"]);
  expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual(["Forecast", "1 to 6 h ahead", "6 to 12 h", "12 to 24 h", "24 to 48 h"]);
  expect(within(within(table).getByRole("row", { name: /^Gridcast/ })).getAllByText("From week 8")).toHaveLength(4);
});

it("says H2 is on track when the interval lies above zero", async () => {
  serve(accuracyBody());
  renderView();
  expect((await screen.findByText(/H2 so far:/)).parentElement?.textContent).toContain("missed by 3.0 g more than those fetched 1 to 6 hours ahead. The 95% interval, 1.3 to 4.5 g, is wholly above zero");
});

it("says the opposite when the interval lies below zero", async () => {
  serve(accuracyBody({ difference: { maeGPerKwh: -2, interval: { low: -3, high: -1 } } }));
  renderView();
  expect((await screen.findByText(/H2 so far:/)).parentElement?.textContent).toContain("missed by 2.0 g less than those fetched 1 to 6 hours ahead. The 95% interval, -3.0 to -1.0 g, is wholly below zero");
});

it.each([
  [0.4, "more"],
  [-0.4, "less"],
])("says the two cannot be told apart when the interval includes zero (%s g)", async (difference, direction) => {
  serve(accuracyBody({ difference: { maeGPerKwh: difference, interval: { low: -1, high: 1 } } }));
  renderView();
  expect((await screen.findByText(/H2 so far:/)).parentElement?.textContent).toContain(`missed by 0.4 g ${direction} than those fetched 1 to 6 hours ahead, but the 95% interval, -1.0 to 1.0 g, includes zero, so the two cannot yet be told apart`);
});

it("states the days measured so far, and no interval, when there are too few", async () => {
  serve(
    accuracyBody({
      bands: EDGES.map(([fromHours, toHours]) => ({ fromHours, toHours, pairs: 100, maeGPerKwh: 9, interval: null })),
      difference: { maeGPerKwh: 2, interval: null },
      days: { usable: ["2026-11-21", "2026-11-22", "2026-11-23"], excluded: [] },
    }),
  );
  renderView();
  const reading = (await screen.findByText(/H2 so far:/)).parentElement;
  expect(reading?.textContent).toContain("3 full days measured. The interval, and so any reading of H2, needs 7.");
  expect(screen.queryByText(/ to .* g$/)).toBeNull();
  expect(screen.getAllByText("9.0 g")).toHaveLength(4);
});

it("says no full day has been measured when there are none", async () => {
  serve(
    accuracyBody({
      bands: EDGES.map(([fromHours, toHours]) => ({ fromHours, toHours, pairs: 0, maeGPerKwh: null, interval: null })),
      difference: { maeGPerKwh: null, interval: null },
      days: { usable: [], excluded: [] },
    }),
  );
  renderView();
  expect((await screen.findByText(/H2 so far:/)).parentElement?.textContent).toContain("no full day has been measured yet.");
  expect(screen.getAllByText("Not enough days yet")).toHaveLength(4);
});

it("counts one day in the singular", async () => {
  serve(accuracyBody({ difference: { maeGPerKwh: 2, interval: null }, days: { usable: ["2026-11-21"], excluded: [] } }));
  renderView();
  expect((await screen.findByText(/H2 so far:/)).parentElement?.textContent).toContain("1 full day measured.");
});

it("lists the days left out with their reasons", async () => {
  serve(accuracyBody());
  renderView();
  const summary = await screen.findByText("2 full days measured, 1 left out");
  fireEvent.click(summary);
  expect(screen.getByText(/only 40 of 48 actuals stored/).parentElement?.textContent).toBe("20 Nov: only 40 of 48 actuals stored");
  expect(screen.getByText(/up to but not including 28 Nov/)).toBeTruthy();
});

it("keeps the pilot and the four tests on the page whatever the live figures do", async () => {
  serve({}, 503);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  renderView();
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByText("9.3 g")).toBeTruthy();
  expect(screen.getAllByRole("listitem").filter((item) => /^H\d/.test(item.textContent)).map((item) => item.textContent.slice(0, 2))).toEqual(["H1", "H2", "H3", "H4"]);
  expect(screen.getByRole("img", { name: /average error by hour of day, 2025/i })).toBeTruthy();
});

it("loads again when asked after a failure", async () => {
  const fake = serve({}, 503);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  renderView();
  fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(fake).toHaveBeenCalledTimes(2);
});

it("says the figures are loading before the answer arrives", () => {
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)));
  renderView();
  expect(screen.getByText("Loading the measured figures…")).toBeTruthy();
});
