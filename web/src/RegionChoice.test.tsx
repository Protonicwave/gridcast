import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { rampColour } from "./chartGeometry";

/** 15:10 on Thursday 19 November 2026, UK time. */
const NOW_MS = Date.parse("2026-11-19T15:10Z");
const SLOT_COUNT = 96;

/** Each region's series is flat at its id times ten, except Yorkshire, which dips at 02:00 so its timing matters. */
function outlook(regionId: number, name: string): Record<string, unknown> {
  const dip = regionId === 5;
  const intensities = Array.from({ length: SLOT_COUNT }, (_, slot) => (dip && slot >= 22 && slot < 28 ? 20 : regionId * 10));
  const flat = (mean: number) => ({ cleanest: { start: 0, mean }, dirtiest: { start: 40, mean }, timingMatters: false });
  const windows = dip
    ? { "3": { cleanest: { start: 22, mean: 20 }, dirtiest: { start: 0, mean: 50 }, timingMatters: true } }
    : { "3": flat(regionId * 10) };
  return { regionId, regionName: name, fetchedAt: "2026-11-19T15:05:12Z", firstSlotStart: "2026-11-19T15:00Z", slotMinutes: 30, intensities, windows };
}

const NAMES = ["North Scotland", "South Scotland", "North West England", "North East England", "Yorkshire", "North Wales", "South Wales", "West Midlands", "East Midlands", "East England", "South West England", "South England", "London", "South East England"];

function urlOf(input: Parameters<typeof fetch>[0]): string {
  if (typeof input === "string") return input;
  return input instanceof URL ? input.href : input.url;
}

function stubNetwork(postcodeResponse: () => Promise<Response> = () => Promise.resolve(new Response(JSON.stringify({ data: [{ regionid: 7 }] })))) {
  const fake = vi.fn<typeof fetch>((input) => {
    if (urlOf(input).includes("postcode")) return postcodeResponse();
    return Promise.resolve(new Response(JSON.stringify(NAMES.map((name, index) => outlook(index + 1, name)))));
  });
  vi.stubGlobal("fetch", fake);
  return fake;
}

function renderApp() {
  return render(<App apiBaseUrl="" now={() => NOW_MS} />);
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

it("asks for a postcode or a region before showing any forecast", async () => {
  stubNetwork();
  const { container } = renderApp();
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("When is your electricity cleanest?");
  expect(container.querySelector("path.series")).toBeNull();
  expect(screen.getByRole("button", { name: "Find region" })).toBeTruthy();
});

it("treats an unknown region in the address as no region", async () => {
  window.history.replaceState(null, "", "/?region=99");
  stubNetwork();
  renderApp();
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("When is your electricity cleanest?");
});

it("lists the regions by cleanest mean, then name", async () => {
  stubNetwork();
  renderApp();
  const rows = within(await screen.findByRole("list")).getAllByRole("button");
  expect(rows.map((row) => row.querySelector(".region-row__name")?.textContent)).toEqual([
    "North Scotland",
    "South Scotland",
    "Yorkshire",
    "North West England",
    "North East England",
    "North Wales",
    "South Wales",
    "West Midlands",
    "East Midlands",
    "East England",
    "South West England",
    "South England",
    "London",
    "South East England",
  ]);
});

it("shows when each region is cleanest, or that any time will do", async () => {
  stubNetwork();
  renderApp();
  const list = within(await screen.findByRole("list"));
  expect(list.getByRole("button", { name: /^Yorkshire/ }).querySelector(".region-row__when")?.textContent).toBe("Tonight 02:00, 20 g");
  expect(list.getByRole("button", { name: /^North Scotland/ }).querySelector(".region-row__when")?.textContent).toBe("Any time, about 10 g");
});

it("shows the region a list row is pressed for, and puts it in the address", async () => {
  stubNetwork();
  const { container } = renderApp();
  const london = within(await screen.findByRole("list")).getByRole("button", { name: /^London/ });
  expect(london.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(london);
  expect(await screen.findByRole("heading", { level: 2, name: "Next 48 hours in London" })).toBeTruthy();
  expect(container.querySelector("path.series")).not.toBeNull();
  expect(window.location.search).toBe("?region=13");
  expect(within(screen.getByRole("list", { name: /Every region/ })).getByRole("button", { name: /^London/ }).getAttribute("aria-pressed")).toBe("true");
});

it("shows the region a postcode belongs to", async () => {
  const fake = stubNetwork();
  renderApp();
  await screen.findByRole("heading", { level: 1 });
  fireEvent.change(screen.getByLabelText("Your postcode"), { target: { value: "CF10 1AA" } });
  fireEvent.click(screen.getByRole("button", { name: "Find region" }));
  expect(await screen.findByRole("heading", { level: 2, name: "Next 48 hours in South Wales" })).toBeTruthy();
  expect(fake.mock.calls.map(([url]) => urlOf(url))).toContain("https://api.carbonintensity.org.uk/regional/postcode/CF10");
  expect(window.location.search).toBe("?region=7");
});

it("keeps the chosen length when the region changes", async () => {
  window.history.replaceState(null, "", "/?region=13&hours=3");
  stubNetwork();
  renderApp();
  await screen.findByRole("heading", { level: 2, name: "Next 48 hours in London" });
  fireEvent.click(within(screen.getByRole("list", { name: /Every region/ })).getByRole("button", { name: /^Yorkshire/ }));
  expect((await screen.findAllByRole("heading", { level: 1 }))[0]?.textContent).toBe("Tonight, 02:00 to 05:00");
  expect(window.location.search).toBe("?region=5");
});

it("tells the visitor what is wrong with a postcode, without calling NESO", async () => {
  const fake = stubNetwork();
  renderApp();
  await screen.findByRole("heading", { level: 1 });
  fireEvent.change(screen.getByLabelText("Your postcode"), { target: { value: "BT1 1AA" } });
  fireEvent.click(screen.getByRole("button", { name: "Find region" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Northern Ireland");
  expect(fake.mock.calls.some(([url]) => urlOf(url).includes("postcode"))).toBe(false);
  expect(screen.getByLabelText("Your postcode").getAttribute("aria-invalid")).toBe("true");
});

it("says so when NESO cannot place the postcode, and leaves the page as it was", async () => {
  stubNetwork(() => Promise.resolve(new Response("{}", { status: 400 })));
  renderApp();
  await screen.findByRole("heading", { level: 1 });
  fireEvent.change(screen.getByLabelText("Your postcode"), { target: { value: "ZZ9" } });
  fireEvent.click(screen.getByRole("button", { name: "Find region" }));
  expect((await screen.findByRole("alert")).textContent).toContain("NESO's lookup didn't find ZZ9");
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("When is your electricity cleanest?");
  expect(window.location.search).toBe("");
});

it("uses the newer lookup when a second one starts before the first answers", async () => {
  let calls = 0;
  stubNetwork((): Promise<Response> => {
    calls += 1;
    if (calls === 1) return new Promise<Response>(() => undefined);
    return Promise.resolve(new Response(JSON.stringify({ data: [{ regionid: 13 }] })));
  });
  const fake = vi.mocked(fetch);
  renderApp();
  await screen.findByRole("heading", { level: 1 });
  const submit = () => {
    fireEvent.click(screen.getByRole("button", { name: /Find|Finding/ }));
  };
  fireEvent.change(screen.getByLabelText("Your postcode"), { target: { value: "BS1" } });
  submit();
  await waitFor(() => {
    expect(calls).toBe(1);
  });
  const firstSignal = fake.mock.calls.find(([url]) => urlOf(url).includes("postcode"))?.[1]?.signal;
  submit();
  expect(await screen.findByRole("heading", { level: 2, name: "Next 48 hours in London" })).toBeTruthy();
  expect(firstSignal?.aborted).toBe(true);
});

it("selects a region by clicking it on the map", async () => {
  stubNetwork();
  const { container } = renderApp();
  await waitFor(() => { expect(container.querySelectorAll("path.region")).toHaveLength(14); });
  fireEvent.click(container.querySelectorAll("path.region")[12] as Element);
  expect(await screen.findByRole("heading", { level: 2, name: "Next 48 hours in London" })).toBeTruthy();
  expect(window.location.search).toBe("?region=13");
  expect(container.querySelectorAll("path.region--selected")).toHaveLength(1);
});

it("recolours the map when the chart's cursor moves", async () => {
  window.history.replaceState(null, "", "/?region=5");
  stubNetwork();
  const { container } = renderApp();
  await waitFor(() => { expect(container.querySelectorAll("path.region")).toHaveLength(14); });
  const fills = () => [...container.querySelectorAll("path.region")].map((path) => path.getAttribute("fill"));
  const atStart = fills();
  const slider = await screen.findByRole("slider");
  // Two pages of twelve half hours reach 02:00, where only Yorkshire dips.
  fireEvent.keyDown(slider, { key: "PageDown" });
  fireEvent.keyDown(slider, { key: "PageDown" });
  const atDip = fills();
  expect(atDip[4]).toBe(rampColour(20));
  expect(atStart[4]).toBe(rampColour(50));
  expect(atDip.filter((_, index) => index !== 4)).toEqual(atStart.filter((_, index) => index !== 4));
});
