/** What the page address records: the chosen region and window length. */

import { DURATIONS_HOURS, type DurationHours, isRegionId } from "./forecastApi";

const DEFAULT_HOURS: DurationHours = 3;

export interface UrlState {
  /** Null until the visitor chooses a region. */
  readonly regionId: number | null;
  readonly hours: DurationHours;
}

/** The state in a query string such as "?region=13&hours=2". Anything else falls back to the default. */
export function parseUrlState(search: string): UrlState {
  const params = new URLSearchParams(search);
  const region = params.get("region");
  const regionId = region !== null && /^\d+$/.test(region) ? Number(region) : Number.NaN;
  const requestedHours = Number(params.get("hours"));
  return {
    regionId: isRegionId(regionId) ? regionId : null,
    hours: DURATIONS_HOURS.find((hours) => hours === requestedHours) ?? DEFAULT_HOURS,
  };
}

/** `href` with the query string replaced by `state`'s non-default parts; the hash is kept. */
export function urlWithState(href: string, state: UrlState): string {
  const url = new URL(href);
  const params = new URLSearchParams();
  if (state.regionId !== null) params.set("region", String(state.regionId));
  if (state.hours !== DEFAULT_HOURS) params.set("hours", String(state.hours));
  url.search = params.toString();
  return url.toString();
}

export type View = "forecast" | "accuracy";

/** The view a page address names, such as "#accuracy". Anything else is the forecast. */
export function parseView(hash: string): View {
  return hash === "#accuracy" ? "accuracy" : "forecast";
}
