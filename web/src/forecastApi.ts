/** Fetches a region's outlook from the Gridcast API and checks it before anything draws it. */

export const DURATIONS_HOURS = [1, 2, 3, 4] as const;
export type DurationHours = (typeof DURATIONS_HOURS)[number];

export interface ForecastWindow {
  /** Index of the window's first half hour in `Outlook.intensities`. */
  readonly start: number;
  readonly meanGPerKwh: number;
}

export interface DurationWindows {
  readonly cleanest: ForecastWindow;
  readonly dirtiest: ForecastWindow;
  readonly timingMatters: boolean;
}

export interface Outlook {
  readonly regionName: string;
  readonly fetchedAtMs: number;
  /** Start of the half hour that held the request time; `intensities[0]` is that half hour. */
  readonly firstSlotStartMs: number;
  readonly slotMs: number;
  readonly intensities: readonly number[];
  /** Only the durations that fit in what remains of the forecast, in increasing order. */
  readonly windows: ReadonlyMap<DurationHours, DurationWindows>;
}

/** The outlook could not be fetched, or the API sent something other than an outlook. */
export class OutlookUnavailableError extends Error {
  override name = "OutlookUnavailableError";
}

const FETCH_TIMEOUT_MS = 10_000;
const SLOT_MINUTES = 30;
const SLOTS_PER_HOUR = 60 / SLOT_MINUTES;
/** Twice NESO's 48-hour forecast: a longer series is not from this feed. */
const MAX_SLOT_COUNT = 192;
const UTC_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$/;
const DURATION_BY_KEY = new Map(DURATIONS_HOURS.map((hours) => [String(hours), hours]));

/**
 * The outlook for `regionId` from the API at `apiBaseUrl` (empty for the page's own origin).
 *
 * Rejects with OutlookUnavailableError, naming the problem, when the API cannot be reached within
 * 10 seconds, answers with another status, or sends a malformed outlook. An abort through `signal`
 * rejects with the abort's own error.
 */
export async function fetchOutlook(apiBaseUrl: string, regionId: number, signal: AbortSignal): Promise<Outlook> {
  const url = `${apiBaseUrl}/regions/${String(regionId)}/outlook`;
  let response: Response;
  try {
    response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(FETCH_TIMEOUT_MS)]) });
  } catch (error: unknown) {
    if (signal.aborted) throw error;
    throw new OutlookUnavailableError(`could not reach ${url}`, { cause: error });
  }
  if (!response.ok) {
    throw new OutlookUnavailableError(`expected HTTP 200 from ${url}, got ${String(response.status)}`);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (error: unknown) {
    if (signal.aborted) throw error;
    throw new OutlookUnavailableError(`expected JSON from ${url}`, { cause: error });
  }
  return parseOutlook(payload, regionId);
}

type Fields = Readonly<Record<string, unknown>>;

function parseOutlook(payload: unknown, regionId: number): Outlook {
  const body = requireObject(payload, "the outlook");
  if (body["regionId"] !== regionId) fail(`regionId ${String(regionId)}`, body["regionId"]);
  const regionName = body["regionName"];
  if (typeof regionName !== "string" || regionName === "") fail("regionName to be a non-empty string", regionName);
  if (body["slotMinutes"] !== SLOT_MINUTES) fail(`slotMinutes ${String(SLOT_MINUTES)}`, body["slotMinutes"]);
  const intensities = parseIntensities(body["intensities"]);
  return {
    regionName,
    fetchedAtMs: parseUtcTime(body["fetchedAt"], "fetchedAt"),
    firstSlotStartMs: parseUtcTime(body["firstSlotStart"], "firstSlotStart"),
    slotMs: SLOT_MINUTES * 60_000,
    intensities,
    windows: parseWindows(body["windows"], intensities.length),
  };
}

function parseUtcTime(value: unknown, name: string): number {
  const ms = typeof value === "string" && UTC_TIME_PATTERN.test(value) ? Date.parse(value) : Number.NaN;
  if (Number.isNaN(ms)) fail(`${name} to be a UTC time such as 2026-11-19T14:05Z`, value);
  return ms;
}

function parseIntensities(value: unknown): readonly number[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_SLOT_COUNT) {
    const shown = Array.isArray(value) ? `${String(value.length)} values` : describe(value);
    throw new OutlookUnavailableError(`expected intensities to be a list of 1 to ${String(MAX_SLOT_COUNT)} values, got ${shown}`);
  }
  return value.map((item: unknown, i) => {
    if (!Number.isInteger(item) || (item as number) < 0) fail(`intensities[${String(i)}] to be a whole number of g per kWh`, item);
    return item as number;
  });
}

function parseWindows(value: unknown, slotCount: number): ReadonlyMap<DurationHours, DurationWindows> {
  const fields = requireObject(value, "windows");
  const parsed = new Map<DurationHours, DurationWindows>();
  for (const [key, entry] of Object.entries(fields)) {
    const hours = DURATION_BY_KEY.get(key);
    if (hours === undefined) fail("window durations from 1 to 4 hours", key);
    const name = `windows["${key}"]`;
    const windows = requireObject(entry, name);
    const lastStart = slotCount - hours * SLOTS_PER_HOUR;
    const timingMatters = windows["timingMatters"];
    if (typeof timingMatters !== "boolean") fail(`${name}.timingMatters to be true or false`, timingMatters);
    parsed.set(hours, {
      cleanest: parseWindow(windows["cleanest"], `${name}.cleanest`, lastStart),
      dirtiest: parseWindow(windows["dirtiest"], `${name}.dirtiest`, lastStart),
      timingMatters,
    });
  }
  if (parsed.size === 0) throw new OutlookUnavailableError("expected windows for at least one duration, got none");
  return new Map(DURATIONS_HOURS.flatMap((hours) => {
    const found = parsed.get(hours);
    return found === undefined ? [] : [[hours, found] as const];
  }));
}

function parseWindow(value: unknown, name: string, lastStart: number): ForecastWindow {
  const fields = requireObject(value, name);
  const start = fields["start"];
  if (!Number.isInteger(start) || (start as number) < 0 || (start as number) > lastStart) {
    fail(`${name}.start to be a whole number from 0 to ${String(lastStart)}`, start);
  }
  const mean = fields["mean"];
  if (typeof mean !== "number" || !Number.isFinite(mean) || mean < 0) {
    fail(`${name}.mean to be a non-negative number of g per kWh`, mean);
  }
  return { start: start as number, meanGPerKwh: mean };
}

function requireObject(value: unknown, name: string): Fields {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail(`${name} to be an object`, value);
  return value as Fields;
}

function fail(expected: string, got: unknown): never {
  throw new OutlookUnavailableError(`expected ${expected}, got ${describe(got)}`);
}

function describe(value: unknown): string {
  if (Array.isArray(value)) return "array";
  return value === undefined ? "undefined" : JSON.stringify(value);
}
