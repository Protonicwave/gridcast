import { expect, it, vi } from "vitest";
import { AccuracyUnavailableError, fetchAccuracy } from "./accuracyApi";

const BAND_EDGES = [
  [1, 6],
  [6, 12],
  [12, 24],
  [24, 48],
] as const;

type Body = Record<string, unknown>;

function validBody(): Body {
  return {
    until: "2026-11-28",
    bands: BAND_EDGES.map(([fromHours, toHours], index) => ({
      fromHours,
      toHours,
      pairs: 4000 + index,
      maeGPerKwh: 8 + index,
      interval: { low: 7 + index, high: 9 + index },
    })),
    difference: { maeGPerKwh: 3, interval: { low: 1.5, high: 4.5 } },
    days: { usable: ["2026-11-21", "2026-11-22"], excluded: [{ day: "2026-11-20", reason: "only 40 of 48 actuals stored" }] },
  };
}

function bodyWith(change: (body: Body) => void): Body {
  const body = validBody();
  change(body);
  return body;
}

/** A valid body whose band `index` has `changes` applied. */
function withBand(index: number, changes: Body): Body {
  return bodyWith((body) => {
    const bands = body["bands"] as Body[];
    bands[index] = { ...bands[index], ...changes };
  });
}

function withDays(days: unknown): Body {
  return bodyWith((body) => {
    body["days"] = days;
  });
}

function respondWith(body: unknown, status = 200) {
  const fake = vi.fn<typeof fetch>(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
  vi.stubGlobal("fetch", fake);
  return fake;
}

async function failureMessage(promise: Promise<unknown>): Promise<string> {
  const error: unknown = await promise.then(
    () => null,
    (reason: unknown) => reason,
  );
  if (!(error instanceof AccuracyUnavailableError)) throw new Error("expected an AccuracyUnavailableError");
  return error.message;
}

const fetchIt = (signal = new AbortController().signal) => fetchAccuracy("https://api.example", signal);

it("reads the bands, the difference and the days", async () => {
  const fake = respondWith(validBody());
  const accuracy = await fetchIt();
  expect(fake.mock.calls[0]?.[0]).toBe("https://api.example/accuracy/national");
  expect(accuracy.until).toBe("2026-11-28");
  expect(accuracy.bands.map((band) => [band.fromHours, band.toHours, band.pairs])).toEqual([
    [1, 6, 4000],
    [6, 12, 4001],
    [12, 24, 4002],
    [24, 48, 4003],
  ]);
  expect(accuracy.bands[3]?.estimate).toEqual({ maeGPerKwh: 11, interval: { low: 10, high: 12 } });
  expect(accuracy.difference).toEqual({ maeGPerKwh: 3, interval: { low: 1.5, high: 4.5 } });
  expect(accuracy.usableDays).toEqual(["2026-11-21", "2026-11-22"]);
  expect(accuracy.excludedDays).toEqual([{ day: "2026-11-20", reason: "only 40 of 48 actuals stored" }]);
});

it("accepts null figures and intervals when there are too few days", async () => {
  respondWith(
    bodyWith((body) => {
      body["bands"] = BAND_EDGES.map(([fromHours, toHours]) => ({ fromHours, toHours, pairs: 0, maeGPerKwh: null, interval: null }));
      body["difference"] = { maeGPerKwh: null, interval: null };
      body["days"] = { usable: [], excluded: [] };
    }),
  );
  const accuracy = await fetchIt();
  expect(accuracy.difference).toEqual({ maeGPerKwh: null, interval: null });
  expect(accuracy.bands[0]?.estimate).toEqual({ maeGPerKwh: null, interval: null });
});

it("accepts a figure without an interval", async () => {
  respondWith(withBand(0, { interval: null }));
  expect((await fetchIt()).bands[0]?.estimate).toEqual({ maeGPerKwh: 8, interval: null });
});

it("accepts a negative difference", async () => {
  respondWith(
    bodyWith((body) => {
      body["difference"] = { maeGPerKwh: -2, interval: { low: -3, high: -1 } };
    }),
  );
  expect((await fetchIt()).difference).toEqual({ maeGPerKwh: -2, interval: { low: -3, high: -1 } });
});

it("reports an unreachable API", async () => {
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => Promise.reject(new TypeError("offline"))));
  expect(await failureMessage(fetchIt())).toBe("could not reach https://api.example/accuracy/national");
});

it("rethrows the abort when the caller aborted", async () => {
  const controller = new AbortController();
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => Promise.reject(new DOMException("aborted", "AbortError"))));
  controller.abort();
  await expect(fetchIt(controller.signal)).rejects.toThrow("aborted");
});

it("rejects another status, naming it", async () => {
  respondWith({}, 503);
  expect(await failureMessage(fetchIt())).toBe("expected HTTP 200 from https://api.example/accuracy/national, got 503");
});

it("rejects a body that is not JSON", async () => {
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => Promise.resolve(new Response("<html>", { status: 200 }))));
  expect(await failureMessage(fetchIt())).toBe("expected JSON from https://api.example/accuracy/national");
});

it("rethrows the abort when the caller aborted while the body was read", async () => {
  const controller = new AbortController();
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(() => {
      controller.abort();
      return Promise.resolve(new Response("{", { status: 200 }));
    }),
  );
  await expect(fetchIt(controller.signal)).rejects.toThrow();
});

const TOO_MANY_DAYS = Array.from({ length: 401 }, () => "2026-11-21");

it.each<[string, () => unknown, string]>([
  ["a body that is not an object", () => [], "expected the accuracy to be an object, got array"],
  ["a malformed until", () => bodyWith((body) => { body["until"] = "28/11/2026"; }), 'expected until to be a date such as 2026-11-28, got "28/11/2026"'],
  ["no bands", () => bodyWith((body) => { body["bands"] = []; }), "expected 4 bands, got 0 bands"],
  ["bands that are not a list", () => bodyWith((body) => { body["bands"] = "none"; }), 'expected 4 bands, got "none"'],
  ["a band that is not an object", () => bodyWith((body) => { (body["bands"] as unknown[])[1] = 3; }), "expected bands[1] to be an object, got 3"],
  ["a band over the wrong hours", () => withBand(2, { toHours: 30 }), "expected bands[2] to span 12 to 24 hours, got 12 to 30"],
  ["a negative pair count", () => withBand(0, { pairs: -1 }), "expected bands[0].pairs to be a whole number of pairs, got -1"],
  ["a fractional pair count", () => withBand(0, { pairs: 2.5 }), "expected bands[0].pairs to be a whole number of pairs, got 2.5"],
  ["a negative error", () => withBand(0, { maeGPerKwh: -1 }), "expected bands[0].maeGPerKwh to be null or a non-negative number of g per kWh, got -1"],
  ["a text error", () => withBand(0, { maeGPerKwh: "8" }), 'expected bands[0].maeGPerKwh to be null or a non-negative number of g per kWh, got "8"'],
  ["an interval that is not an object", () => withBand(3, { interval: 5 }), "expected bands[3].interval to be null or an object, got 5"],
  ["an interval upside down", () => withBand(3, { interval: { low: 9, high: 8 } }), "expected bands[3].interval to run from a low to a higher number, got 9 to 8"],
  ["an interval with no figure", () => withBand(3, { maeGPerKwh: null }), "expected bands[3] to have a figure when it has an interval"],
  ["a missing difference", () => bodyWith((body) => { delete body["difference"]; }), "expected difference to be an object, got undefined"],
  ["a non-numeric difference", () => bodyWith((body) => { body["difference"] = { maeGPerKwh: "3", interval: null }; }), 'expected difference.maeGPerKwh to be null or a number of g per kWh, got "3"'],
  ["missing days", () => bodyWith((body) => { delete body["days"]; }), "expected days to be an object, got undefined"],
  ["usable days that are not dates", () => withDays({ usable: ["soon"], excluded: [] }), 'expected days.usable[0] to be a date such as 2026-11-28, got "soon"'],
  ["usable days that are not a list", () => withDays({ usable: "all", excluded: [] }), 'expected days.usable to be a list of at most 400 days, got "all"'],
  ["too many days", () => withDays({ usable: TOO_MANY_DAYS, excluded: [] }), "expected days.usable to be a list of at most 400 days, got 401 days"],
  ["an excluded day with no reason", () => withDays({ usable: [], excluded: [{ day: "2026-11-20", reason: "" }] }), 'expected days.excluded[0].reason to be a non-empty string, got ""'],
  ["an excluded day that is not an object", () => withDays({ usable: [], excluded: ["2026-11-20"] }), 'expected days.excluded[0] to be an object, got "2026-11-20"'],
])("rejects %s", async (_name, makeBody, expected) => {
  respondWith(makeBody());
  expect(await failureMessage(fetchIt())).toBe(expected);
});
