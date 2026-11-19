import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";

const MINUTE_MS = 60_000;
/** 15:10 on Thursday 19 November 2026, UK time. */
const NOW_MS = Date.parse("2026-11-19T15:10Z");

/**
 * 48 hours from 15:00: 200 g, except 250 g from 16:00 to 20:00, 90 g from 22:00 and 80 g from 01:00 to 02:00.
 * The windows below are the ones the API computes for this series.
 */
function londonIntensities(): number[] {
  return Array.from({ length: 96 }, (_, slot) => {
    if (slot >= 2 && slot < 10) return 250;
    if (slot >= 20 && slot < 22) return 80;
    if (slot >= 14 && slot < 20) return 90;
    return 200;
  });
}

function londonOutlook(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    regionId: 13,
    regionName: "London",
    fetchedAt: "2026-11-19T15:05:12Z",
    firstSlotStart: "2026-11-19T15:00Z",
    slotMinutes: 30,
    intensities: londonIntensities(),
    windows: {
      "1": { cleanest: { start: 20, mean: 80 }, dirtiest: { start: 2, mean: 250 }, timingMatters: true },
      "2": { cleanest: { start: 18, mean: 85 }, dirtiest: { start: 2, mean: 250 }, timingMatters: true },
      "3": { cleanest: { start: 16, mean: 86.7 }, dirtiest: { start: 2, mean: 250 }, timingMatters: true },
      "4": { cleanest: { start: 14, mean: 87.5 }, dirtiest: { start: 2, mean: 250 }, timingMatters: true },
    },
    ...overrides,
  };
}

function serve(...bodies: { readonly status: number; readonly body: unknown }[]) {
  const queue = [...bodies];
  const fake = vi.fn<typeof fetch>(() => {
    const next = queue.shift();
    if (next === undefined) return new Promise<Response>(() => undefined);
    return Promise.resolve(new Response(JSON.stringify(next.body), { status: next.status }));
  });
  vi.stubGlobal("fetch", fake);
  return fake;
}

function renderApp(now: () => number = () => NOW_MS) {
  return render(<App apiBaseUrl="" now={now} />);
}

async function heading() {
  return (await screen.findByRole("heading", { level: 1 })).textContent;
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

it("shows no loading text for the first 200 ms, then says it is loading", async () => {
  serve();
  renderApp();
  expect(screen.queryByText("Loading the forecast…")).toBeNull();
  expect(await screen.findByText("Loading the forecast…")).toBeTruthy();
});

it("answers with London's cleanest three hours and draws the series", async () => {
  serve({ status: 200, body: londonOutlook() });
  const { container } = renderApp();
  expect(await heading()).toBe("Tonight, 23:00 to 02:00");
  expect(screen.getByText("Cleanest three hours in London")).toBeTruthy();
  expect(screen.getByText("Forecast fetched 15:05, Thursday 19 November. NESO updates it every half hour.")).toBeTruthy();
  expect(screen.getByRole("heading", { level: 2, name: "Next 48 hours in London" })).toBeTruthy();
  expect(container.querySelector("path.series")?.getAttribute("d")).toMatch(/^M36\.0 /);
  expect(screen.queryByRole("status")).toBeNull();
});

it("calls the API for London", async () => {
  const fake = serve({ status: 200, body: londonOutlook() });
  renderApp();
  await heading();
  expect(fake.mock.calls[0]?.[0]).toBe("/regions/13/outlook");
});

it("warns when the forecast is older than 75 minutes", async () => {
  serve({ status: 200, body: londonOutlook({ fetchedAt: "2026-11-19T13:05Z" }) });
  renderApp();
  expect((await screen.findByRole("status")).textContent).toContain("This forecast is 2 hours old.");
});

it("says any time works when timing makes little difference", async () => {
  const windows = { "3": { cleanest: { start: 0, mean: 199.6 }, dirtiest: { start: 40, mean: 201.2 }, timingMatters: false } };
  serve({ status: 200, body: londonOutlook({ windows }) });
  const { container } = renderApp();
  expect(await heading()).toBe("Any time works about as well");
  expect(container.querySelector(".answer__detail")?.textContent).toBe(
    "Every three-hour window averages between 200 g and 201 g of CO2 per kWh, so there is little to gain by waiting.",
  );
  expect(container.querySelector(".window-band")).toBeNull();
});

it("shows the unavailable state when the API fails, and recovers on retry", async () => {
  const fake = serve({ status: 503, body: { detail: "the forecast archive is unavailable" } }, { status: 200, body: londonOutlook() });
  renderApp();
  expect((await screen.findByRole("alert")).textContent).toContain("Gridcast can't load the forecast right now.");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await heading()).toBe("Tonight, 23:00 to 02:00");
  expect(fake).toHaveBeenCalledTimes(2);
});

it("shows the unavailable state for a payload of the wrong shape", async () => {
  serve({ status: 200, body: londonOutlook({ intensities: "none" }) });
  renderApp();
  expect(await screen.findByRole("alert")).toBeTruthy();
});

it("moves the answer and the band when the duration changes, and keeps it in the address", async () => {
  serve({ status: 200, body: londonOutlook() });
  const { container } = renderApp();
  await heading();
  const bandWidth = () => Number(container.querySelector(".window-band")?.getAttribute("width"));
  const threeHourWidth = bandWidth();
  fireEvent.click(screen.getByLabelText("1 h"));
  expect(await heading()).toBe("Tonight, 01:00 to 02:00");
  expect(bandWidth()).toBeCloseTo(threeHourWidth / 3);
  expect(window.location.search).toBe("?hours=1");
});

it("disables durations longer than what remains of the forecast and shows the longest that fits", async () => {
  window.history.replaceState(null, "", "/?hours=4");
  const windows = { "1": { cleanest: { start: 4, mean: 80 }, dirtiest: { start: 0, mean: 250 }, timingMatters: true } };
  serve({ status: 200, body: londonOutlook({ intensities: [250, 250, 200, 200, 80, 80], windows }) });
  renderApp();
  expect(await heading()).toBe("Today, 17:00 to 18:00");
  expect(screen.getByLabelText<HTMLInputElement>("4 h").disabled).toBe(true);
  expect(screen.getByLabelText<HTMLInputElement>("1 h").checked).toBe(true);
});

it("moves the cursor and the readout with the arrow keys", async () => {
  serve({ status: 200, body: londonOutlook() });
  renderApp();
  await heading();
  const slider = screen.getByRole("slider");
  expect(screen.getByRole("heading", { level: 2, name: "Today, 15:00 to 15:30" })).toBeTruthy();
  fireEvent.keyDown(slider, { key: "ArrowRight" });
  fireEvent.keyDown(slider, { key: "ArrowRight" });
  expect(slider.getAttribute("aria-valuenow")).toBe("2");
  expect(slider.getAttribute("aria-valuetext")).toBe("today 16:00, 250 grams per kilowatt hour");
  expect(screen.getByRole("heading", { level: 2, name: "Today, 16:00 to 16:30" })).toBeTruthy();
  expect(screen.getByText(/^250 g CO/)).toBeTruthy();
  fireEvent.keyDown(slider, { key: "End" });
  fireEvent.keyDown(slider, { key: "ArrowRight" });
  expect(slider.getAttribute("aria-valuenow")).toBe("95");
  fireEvent.keyDown(slider, { key: "Home" });
  fireEvent.keyDown(slider, { key: "ArrowLeft" });
  expect(slider.getAttribute("aria-valuenow")).toBe("0");
});

it("fetches again when the page is shown after more than 10 minutes", async () => {
  let nowMs = NOW_MS;
  const fake = serve({ status: 200, body: londonOutlook() }, { status: 200, body: londonOutlook({ fetchedAt: "2026-11-19T15:35Z" }) });
  renderApp(() => nowMs);
  await heading();
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  nowMs += 9 * MINUTE_MS;
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
  expect(fake).toHaveBeenCalledTimes(1);
  nowMs += 2 * MINUTE_MS;
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await waitFor(() => {
    expect(screen.getByText(/^Forecast fetched 15:35/)).toBeTruthy();
  });
  expect(fake).toHaveBeenCalledTimes(2);
});
