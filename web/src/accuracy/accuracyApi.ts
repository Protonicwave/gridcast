/** Fetches NESO's national forecast error by horizon from the Gridcast API and checks it before anything draws it. */

export interface Interval {
  readonly low: number;
  readonly high: number;
}

/** A mean absolute error in g CO2 per kWh. Both fields are null until enough days have been measured. */
export interface Estimate {
  readonly maeGPerKwh: number | null;
  readonly interval: Interval | null;
}

export interface BandAccuracy {
  readonly fromHours: number;
  readonly toHours: number;
  readonly pairs: number;
  readonly estimate: Estimate;
}

interface ExcludedDay {
  /** A UTC date such as 2026-11-20. */
  readonly day: string;
  readonly reason: string;
}

export interface NationalAccuracy {
  /** The UTC date the evaluation stops before. */
  readonly until: string;
  /** The four bands, nearest forecasts first. */
  readonly bands: readonly BandAccuracy[];
  /** The 24 to 48 hour band's error minus the 1 to 6 hour band's. */
  readonly difference: Estimate;
  readonly usableDays: readonly string[];
  readonly excludedDays: readonly ExcludedDay[];
}

/** The accuracy could not be fetched, or the API sent something other than an accuracy. */
export class AccuracyUnavailableError extends Error {
  override name = "AccuracyUnavailableError";
}

const FETCH_TIMEOUT_MS = 10_000;
/** The API evaluates at most 120 days; a longer list is not from this endpoint. */
const MAX_DAYS = 400;
const BAND_EDGES_HOURS = [
  [1, 6],
  [6, 12],
  [12, 24],
  [24, 48],
] as const;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

type Fields = Readonly<Record<string, unknown>>;

/**
 * The national accuracy from the API at `apiBaseUrl` (empty for the page's own origin).
 *
 * Rejects with AccuracyUnavailableError, naming the problem, when the API cannot be reached
 * within 10 seconds, answers with another status, or sends anything but the four bands, the
 * difference and the days. An abort through `signal` rejects with the abort's own error.
 */
export async function fetchAccuracy(apiBaseUrl: string, signal: AbortSignal): Promise<NationalAccuracy> {
  const url = `${apiBaseUrl}/accuracy/national`;
  let response: Response;
  try {
    response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(FETCH_TIMEOUT_MS)]) });
  } catch (error: unknown) {
    if (signal.aborted) throw error;
    throw new AccuracyUnavailableError(`could not reach ${url}`, { cause: error });
  }
  if (!response.ok) throw new AccuracyUnavailableError(`expected HTTP 200 from ${url}, got ${String(response.status)}`);
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (error: unknown) {
    if (signal.aborted) throw error;
    throw new AccuracyUnavailableError(`expected JSON from ${url}`, { cause: error });
  }
  return parseAccuracy(payload);
}

function parseAccuracy(payload: unknown): NationalAccuracy {
  const body = requireObject(payload, "the accuracy");
  const days = requireObject(body["days"], "days");
  return {
    until: parseDate(body["until"], "until"),
    bands: parseBands(body["bands"]),
    difference: parseEstimate(requireObject(body["difference"], "difference"), "difference", false),
    usableDays: parseList(days["usable"], "days.usable").map((day, i) => parseDate(day, `days.usable[${String(i)}]`)),
    excludedDays: parseList(days["excluded"], "days.excluded").map((entry, i) => parseExcludedDay(entry, i)),
  };
}

function parseBands(value: unknown): readonly BandAccuracy[] {
  if (!Array.isArray(value) || value.length !== BAND_EDGES_HOURS.length) {
    const shown = Array.isArray(value) ? `${String(value.length)} bands` : describe(value);
    throw new AccuracyUnavailableError(`expected ${String(BAND_EDGES_HOURS.length)} bands, got ${shown}`);
  }
  return BAND_EDGES_HOURS.map(([fromHours, toHours], index) => {
    const name = `bands[${String(index)}]`;
    const band = requireObject(value[index], name);
    if (band["fromHours"] !== fromHours || band["toHours"] !== toHours) {
      fail(`${name} to span ${String(fromHours)} to ${String(toHours)} hours`, `${describe(band["fromHours"])} to ${describe(band["toHours"])}`, true);
    }
    const pairs = band["pairs"];
    if (!Number.isInteger(pairs) || (pairs as number) < 0) fail(`${name}.pairs to be a whole number of pairs`, pairs);
    return { fromHours, toHours, pairs: pairs as number, estimate: parseEstimate(band, name, true) };
  });
}

/** `nonNegative` is true for a band's error, which cannot be below zero, and false for the difference, which can. */
function parseEstimate(fields: Fields, name: string, nonNegative: boolean): Estimate {
  const mae = fields["maeGPerKwh"];
  const isValid = typeof mae === "number" && Number.isFinite(mae) && (!nonNegative || mae >= 0);
  if (mae !== null && !isValid) {
    fail(`${name}.maeGPerKwh to be null or a ${nonNegative ? "non-negative " : ""}number of g per kWh`, mae);
  }
  const interval = fields["interval"] === null ? null : parseInterval(fields["interval"], `${name}.interval`);
  if (interval !== null && mae === null) throw new AccuracyUnavailableError(`expected ${name} to have a figure when it has an interval`);
  return { maeGPerKwh: mae, interval };
}

function parseInterval(value: unknown, name: string): Interval {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail(`${name} to be null or an object`, value);
  const { low, high } = value as Fields;
  if (typeof low !== "number" || typeof high !== "number" || !Number.isFinite(low) || !Number.isFinite(high) || low > high) {
    fail(`${name} to run from a low to a higher number`, `${describe(low)} to ${describe(high)}`, true);
  }
  return { low, high };
}

function parseExcludedDay(value: unknown, index: number): ExcludedDay {
  const name = `days.excluded[${String(index)}]`;
  const fields = requireObject(value, name);
  const reason = fields["reason"];
  if (typeof reason !== "string" || reason === "") fail(`${name}.reason to be a non-empty string`, reason);
  return { day: parseDate(fields["day"], `${name}.day`), reason };
}

function parseList(value: unknown, name: string): readonly unknown[] {
  if (!Array.isArray(value) || value.length > MAX_DAYS) {
    const shown = Array.isArray(value) ? `${String(value.length)} days` : describe(value);
    throw new AccuracyUnavailableError(`expected ${name} to be a list of at most ${String(MAX_DAYS)} days, got ${shown}`);
  }
  return value;
}

function parseDate(value: unknown, name: string): string {
  if (typeof value !== "string" || !DATE_PATTERN.test(value) || Number.isNaN(Date.parse(value))) {
    fail(`${name} to be a date such as 2026-11-28`, value);
  }
  return value;
}

function requireObject(value: unknown, name: string): Fields {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail(`${name} to be an object`, value);
  return value as Fields;
}

function fail(expected: string, got: unknown, alreadyDescribed = false): never {
  throw new AccuracyUnavailableError(`expected ${expected}, got ${alreadyDescribed ? String(got) : describe(got)}`);
}

function describe(value: unknown): string {
  if (Array.isArray(value)) return "array";
  return value === undefined ? "undefined" : JSON.stringify(value);
}
