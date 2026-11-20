import { expect, it, vi } from "vitest";
import { fetchOutlooks, OutlookUnavailableError } from "./forecastApi";

const LONDON_ID = 13;
const SIXTY_SLOTS = Array.from({ length: 60 }, (_, i) => 200 - i);

function validBody(): Record<string, unknown> {
  return {
    regionId: LONDON_ID,
    regionName: "London",
    fetchedAt: "2026-11-19T14:05:12Z",
    firstSlotStart: "2026-11-19T14:00Z",
    slotMinutes: 30,
    intensities: [...SIXTY_SLOTS],
    windows: {
      "1": { cleanest: { start: 58, mean: 141.5 }, dirtiest: { start: 0, mean: 199.5 }, timingMatters: true },
      "3": { cleanest: { start: 54, mean: 143.5 }, dirtiest: { start: 0, mean: 197.5 }, timingMatters: false },
    },
  };
}

/** Fourteen outlooks, each region's the same as London's except for its id and name. */
function allRegions(london: unknown): unknown[] {
  return Array.from({ length: 14 }, (_, index) => {
    const regionId = index + 1;
    return regionId === LONDON_ID ? london : { ...validBody(), regionId, regionName: `Region ${String(regionId)}` };
  });
}

function stubFetch(respond: () => Promise<Response>) {
  const fake = vi.fn<typeof fetch>(() => respond());
  vi.stubGlobal("fetch", fake);
  return fake;
}

function respondWith(body: unknown, status = 200) {
  stubFetch(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
}

async function failureMessage(promise: Promise<unknown>): Promise<string> {
  const error: unknown = await promise.then(
    () => null,
    (reason: unknown) => reason,
  );
  if (!(error instanceof OutlookUnavailableError)) throw new Error("expected an OutlookUnavailableError");
  return error.message;
}

async function fetchLondon(signal = new AbortController().signal) {
  const london = (await fetchOutlooks("https://api.example", signal)).get(LONDON_ID);
  if (london === undefined) throw new Error("expected an outlook for London");
  return london;
}

it("requests every region's outlook from the API", async () => {
  respondWith(allRegions(validBody()));
  await fetchLondon();
  const fake = vi.mocked(fetch);
  expect(fake.mock.calls[0]?.[0]).toBe("https://api.example/regions/outlook");
});

it("returns the 14 outlooks by region id", async () => {
  respondWith(allRegions(validBody()));
  const outlooks = await fetchOutlooks("https://api.example", new AbortController().signal);
  expect([...outlooks.keys()]).toEqual(Array.from({ length: 14 }, (_, index) => index + 1));
  expect(outlooks.get(4)?.regionName).toBe("Region 4");
  expect(outlooks.get(4)?.regionId).toBe(4);
});

it.each([
  ["an object", () => ({}), "expected 14 outlooks, got {}"],
  ["null", () => null, "expected 14 outlooks, got null"],
  ["13 outlooks", () => allRegions(validBody()).slice(1), "expected 14 outlooks, got 13 outlooks"],
  ["15 outlooks", () => [...allRegions(validBody()), validBody()], "expected 14 outlooks, got 15 outlooks"],
  ["outlooks out of order", () => allRegions(validBody()).reverse(), "expected regionId 1, got 14"],
])("rejects %s, naming the value", async (_case, body, message) => {
  respondWith(body());
  expect(await failureMessage(fetchLondon())).toBe(message);
});

it("parses a valid payload into times, slots and windows", async () => {
  respondWith(allRegions(validBody()));
  const outlook = await fetchLondon();
  expect(outlook.regionName).toBe("London");
  expect(outlook.fetchedAtMs).toBe(Date.parse("2026-11-19T14:05:12Z"));
  expect(outlook.firstSlotStartMs).toBe(Date.parse("2026-11-19T14:00Z"));
  expect(outlook.slotMs).toBe(1_800_000);
  expect(outlook.intensities).toEqual(SIXTY_SLOTS);
  expect([...outlook.windows.keys()]).toEqual([1, 3]);
  expect(outlook.windows.get(3)).toEqual({
    cleanest: { start: 54, meanGPerKwh: 143.5 },
    dirtiest: { start: 0, meanGPerKwh: 197.5 },
    timingMatters: false,
  });
});

it.each([
  ["a body that is not an object", () => [], "expected the outlook to be an object, got array"],
  ["null", () => null, "expected the outlook to be an object, got null"],
  ["another region", (b: Record<string, unknown>) => ({ ...b, regionId: 12 }), "expected regionId 13, got 12"],
  ["a missing region name", (b: Record<string, unknown>) => ({ ...b, regionName: "" }), 'expected regionName to be a non-empty string, got ""'],
  ["a numeric region name", (b: Record<string, unknown>) => ({ ...b, regionName: 13 }), "expected regionName to be a non-empty string, got 13"],
  ["an unreadable fetch time", (b: Record<string, unknown>) => ({ ...b, fetchedAt: "yesterday" }), 'expected fetchedAt to be a UTC time such as 2026-11-19T14:05Z, got "yesterday"'],
  ["a fetch time without a zone", (b: Record<string, unknown>) => ({ ...b, fetchedAt: "2026-11-19T14:05" }), 'expected fetchedAt to be a UTC time such as 2026-11-19T14:05Z, got "2026-11-19T14:05"'],
  ["an impossible first slot", (b: Record<string, unknown>) => ({ ...b, firstSlotStart: "2026-13-45T14:00Z" }), 'expected firstSlotStart to be a UTC time such as 2026-11-19T14:05Z, got "2026-13-45T14:00Z"'],
  ["hourly slots", (b: Record<string, unknown>) => ({ ...b, slotMinutes: 60 }), "expected slotMinutes 30, got 60"],
  ["intensities that are not a list", (b: Record<string, unknown>) => ({ ...b, intensities: "212" }), 'expected intensities to be a list of 1 to 192 values, got "212"'],
  ["no intensities", (b: Record<string, unknown>) => ({ ...b, intensities: [] }), "expected intensities to be a list of 1 to 192 values, got 0 values"],
  ["too many intensities", (b: Record<string, unknown>) => ({ ...b, intensities: Array<number>(193).fill(100) }), "expected intensities to be a list of 1 to 192 values, got 193 values"],
  ["a negative intensity", (b: Record<string, unknown>) => ({ ...b, intensities: [100, -1] }), "expected intensities[1] to be a whole number of g per kWh, got -1"],
  ["a fractional intensity", (b: Record<string, unknown>) => ({ ...b, intensities: [100.5] }), "expected intensities[0] to be a whole number of g per kWh, got 100.5"],
  ["windows that are a list", (b: Record<string, unknown>) => ({ ...b, windows: [] }), "expected windows to be an object, got array"],
  ["no windows", (b: Record<string, unknown>) => ({ ...b, windows: {} }), "expected windows for at least one duration, got none"],
  ["an unknown duration", (b: Record<string, unknown>) => ({ ...b, windows: { "5": {} } }), 'expected window durations from 1 to 4 hours, got "5"'],
  ["a duration that is not an object", (b: Record<string, unknown>) => ({ ...b, windows: { "1": true } }), 'expected windows["1"] to be an object, got true'],
  ["a missing cleanest window", (b: Record<string, unknown>) => ({ ...b, windows: { "1": { dirtiest: { start: 0, mean: 1 }, timingMatters: true } } }), 'expected windows["1"].cleanest to be an object, got undefined'],
  ["a fractional start", (b: Record<string, unknown>) => ({ ...b, windows: { "1": { cleanest: { start: 1.5, mean: 1 }, dirtiest: { start: 0, mean: 1 }, timingMatters: true } } }), 'expected windows["1"].cleanest.start to be a whole number from 0 to 58, got 1.5'],
  ["a window past the end", (b: Record<string, unknown>) => ({ ...b, windows: { "2": { cleanest: { start: 0, mean: 1 }, dirtiest: { start: 57, mean: 1 }, timingMatters: true } } }), 'expected windows["2"].dirtiest.start to be a whole number from 0 to 56, got 57'],
  ["a negative start", (b: Record<string, unknown>) => ({ ...b, windows: { "1": { cleanest: { start: -1, mean: 1 }, dirtiest: { start: 0, mean: 1 }, timingMatters: true } } }), 'expected windows["1"].cleanest.start to be a whole number from 0 to 58, got -1'],
  ["a negative mean", (b: Record<string, unknown>) => ({ ...b, windows: { "1": { cleanest: { start: 0, mean: -2 }, dirtiest: { start: 0, mean: 1 }, timingMatters: true } } }), 'expected windows["1"].cleanest.mean to be a non-negative number of g per kWh, got -2'],
  ["a textual mean", (b: Record<string, unknown>) => ({ ...b, windows: { "1": { cleanest: { start: 0, mean: "96" }, dirtiest: { start: 0, mean: 1 }, timingMatters: true } } }), 'expected windows["1"].cleanest.mean to be a non-negative number of g per kWh, got "96"'],
  ["a textual verdict", (b: Record<string, unknown>) => ({ ...b, windows: { "1": { cleanest: { start: 0, mean: 1 }, dirtiest: { start: 0, mean: 1 }, timingMatters: "yes" } } }), 'expected windows["1"].timingMatters to be true or false, got "yes"'],
])("rejects %s, naming the value", async (_case, change, message) => {
  respondWith(allRegions(change(validBody())));
  expect(await failureMessage(fetchLondon())).toBe(message);
});

it("rejects a response other than 200, naming the status", async () => {
  respondWith({ detail: "the forecast archive is unavailable" }, 503);
  expect(await failureMessage(fetchLondon())).toBe("expected HTTP 200 from https://api.example/regions/outlook, got 503");
});

it("rejects a body that is not JSON", async () => {
  stubFetch(() => Promise.resolve(new Response("<html>", { status: 200 })));
  expect(await failureMessage(fetchLondon())).toBe("expected JSON from https://api.example/regions/outlook");
});

it("reports a network failure as unavailable, keeping the cause", async () => {
  const cause = new TypeError("Failed to fetch");
  stubFetch(() => Promise.reject(cause));
  const error: unknown = await fetchLondon().catch((reason: unknown) => reason);
  expect(error).toBeInstanceOf(OutlookUnavailableError);
  expect((error as OutlookUnavailableError).message).toBe("could not reach https://api.example/regions/outlook");
  expect((error as OutlookUnavailableError).cause).toBe(cause);
});

it("gives up after 10 seconds", () => {
  const clock = new AbortController();
  const timeout = vi.spyOn(AbortSignal, "timeout").mockReturnValue(clock.signal);
  const fake = stubFetch(() => new Promise<Response>(() => undefined));
  // The request never settles, so the promise is left pending on purpose.
  void fetchLondon();
  const signal = fake.mock.calls[0]?.[1]?.signal;
  expect(timeout).toHaveBeenCalledWith(10_000);
  expect(signal?.aborted).toBe(false);
  clock.abort();
  expect(signal?.aborted).toBe(true);
});

it("passes the caller's abort through rather than reporting the API unavailable", async () => {
  const caller = new AbortController();
  const abort = new DOMException("aborted", "AbortError");
  stubFetch(() => Promise.reject(abort));
  caller.abort();
  await expect(fetchLondon(caller.signal)).rejects.toBe(abort);
});

it("passes the caller's abort through while the body is read", async () => {
  const caller = new AbortController();
  const abort = new DOMException("aborted", "AbortError");
  const response = new Response("{}");
  vi.spyOn(response, "json").mockImplementation(() => {
    caller.abort();
    return Promise.reject(abort);
  });
  stubFetch(() => Promise.resolve(response));
  await expect(fetchLondon(caller.signal)).rejects.toBe(abort);
});
