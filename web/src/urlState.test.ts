import { expect, it } from "vitest";
import { parseUrlState, urlWithState } from "./urlState";

it("defaults to no region and three hours", () => {
  expect(parseUrlState("")).toEqual({ regionId: null, hours: 3 });
});

it.each([
  ["?region=1", 1],
  ["?region=14", 14],
  ["?region=0", null],
  ["?region=15", null],
  ["?region=london", null],
  ["?region=1.5", null],
  ["?region=-3", null],
  ["?region=", null],
])("reads %s as region %s", (search, regionId) => {
  expect(parseUrlState(search).regionId).toBe(regionId);
});

it.each([
  ["?hours=1", 1],
  ["?hours=4", 4],
  ["?hours=5", 3],
  ["?hours=two", 3],
])("reads %s as %s hours", (search, hours) => {
  expect(parseUrlState(search).hours).toBe(hours);
});

it("round-trips a chosen region and length through the address", () => {
  const state = { regionId: 9, hours: 2 } as const;
  const href = urlWithState("https://example.invalid/gridcast/", state);
  expect(href).toBe("https://example.invalid/gridcast/?region=9&hours=2");
  expect(parseUrlState(new URL(href).search)).toEqual(state);
});

it("leaves out what is still at its default and keeps the hash", () => {
  expect(urlWithState("https://example.invalid/?region=3&hours=1#top", { regionId: null, hours: 3 })).toBe("https://example.invalid/#top");
});
