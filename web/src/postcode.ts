/** Finds the network region of a postcode through the Carbon Intensity API's own lookup. */

import { isRegionId } from "./forecastApi";

const LOOKUP_URL = "https://api.carbonintensity.org.uk/regional/postcode/";
const LOOKUP_TIMEOUT_MS = 8_000;
/** A full postcode or its outward half, without the space: "BS14DJ" or "BS1". */
const POSTCODE_PATTERN = /^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})?$/;
const OUTSIDE_GRID_MESSAGES = new Map([
  ["BT", "Northern Ireland has its own electricity grid, which Gridcast does not cover. Gridcast covers England, Scotland and Wales."],
  ["GY", "Gridcast covers England, Scotland and Wales, which share one grid. Guernsey is not part of it."],
  ["JE", "Gridcast covers England, Scotland and Wales, which share one grid. Jersey is not part of it."],
  ["IM", "Gridcast covers England, Scotland and Wales, which share one grid. The Isle of Man is not part of it."],
]);

/** A postcode that cannot be looked up; the message is written for the visitor. */
export class PostcodeError extends Error {
  override name = "PostcodeError";
}

/** The postcode could not be looked up, or NESO's reply was not a region. The message is written for the visitor. */
export class PostcodeLookupError extends Error {
  override name = "PostcodeLookupError";
}

/** The outward code ("BS1") of what the visitor typed, which may be a full postcode. Throws PostcodeError. */
export function outwardCode(input: string): string {
  const cleaned = input.toUpperCase().replace(/\s+/g, "");
  if (cleaned === "") throw new PostcodeError("Enter a postcode, such as BS1 or BS1 4DJ.");
  const outward = POSTCODE_PATTERN.exec(cleaned)?.[1];
  if (outward === undefined) {
    throw new PostcodeError(`"${input.trim()}" doesn't look like a UK postcode. Try the first half, such as BS1.`);
  }
  const outsideGrid = OUTSIDE_GRID_MESSAGES.get(outward.slice(0, 2));
  if (outsideGrid !== undefined) throw new PostcodeError(outsideGrid);
  return outward;
}

/**
 * The region id (1 to 14) NESO gives `outward`. Only the outward code leaves the browser.
 *
 * Rejects with PostcodeLookupError when NESO is unreachable within 8 seconds, answers with an error or
 * names no region. NESO's error responses carry no CORS header, so an unknown postcode and a network
 * failure look the same. An abort through `signal` rejects with the abort's own error.
 */
export async function lookUpRegion(outward: string, signal: AbortSignal): Promise<number> {
  const url = `${LOOKUP_URL}${encodeURIComponent(outward)}`;
  let payload: unknown;
  try {
    const response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(LOOKUP_TIMEOUT_MS)]) });
    if (!response.ok) throw new Error(`expected HTTP 200 from ${url}, got ${String(response.status)}`);
    payload = await response.json();
  } catch (error: unknown) {
    if (signal.aborted) throw error;
    throw new PostcodeLookupError(`NESO's lookup didn't find ${outward}, or couldn't be reached. Check the postcode, or pick your region from the list.`, { cause: error });
  }
  const regionId = regionIdFrom(payload);
  if (regionId === null) {
    throw new PostcodeLookupError(`NESO's lookup gave no region for ${outward}. Check the postcode, or pick your region from the list.`);
  }
  return regionId;
}

function regionIdFrom(payload: unknown): number | null {
  if (typeof payload !== "object" || payload === null || !("data" in payload) || !Array.isArray(payload.data)) return null;
  const first: unknown = payload.data[0];
  if (typeof first !== "object" || first === null || !("regionid" in first)) return null;
  return isRegionId(first.regionid) ? first.regionid : null;
}
