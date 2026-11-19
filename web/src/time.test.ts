import { expect, it } from "vitest";
import {
  ageText,
  agree,
  clock,
  dayWord,
  durationAdjective,
  durationNoun,
  fetchedPhrase,
  grams,
  halfHourPhrase,
  windowPhrase,
} from "./time";

const HALF_HOUR_MS = 1_800_000;
/** 15:00 on Thursday 19 November 2026, UK time (GMT). */
const THURSDAY_AFTERNOON = Date.parse("2026-11-19T15:00Z");
/** 21:00 on Saturday 24 October 2026, UK time (BST); clocks go back at 02:00 BST on Sunday. */
const SATURDAY_BEFORE_CLOCK_CHANGE = Date.parse("2026-10-24T20:00Z");

it.each([
  ["2026-11-19T14:05Z", "14:05"],
  ["2026-06-19T14:05Z", "15:05"],
  ["2026-11-19T23:30Z", "23:30"],
  ["2026-11-20T00:00Z", "00:00"],
  // The same UTC hour either side of the October clock change.
  ["2026-10-25T00:30Z", "01:30"],
  ["2026-10-25T01:30Z", "01:30"],
])("writes %s as the UK clock time %s", (utc, expected) => {
  expect(clock(Date.parse(utc))).toBe(expected);
});

it.each([
  ["2026-11-19T15:30Z", "today"],
  ["2026-11-19T17:59Z", "today"],
  ["2026-11-19T18:00Z", "tonight"],
  ["2026-11-20T05:30Z", "tonight"],
  ["2026-11-20T06:00Z", "tomorrow"],
  ["2026-11-20T23:30Z", "tomorrow"],
  ["2026-11-21T05:30Z", "tomorrow night"],
  ["2026-11-21T06:00Z", "Saturday"],
])("calls %s %s when it is Thursday afternoon", (utc, expected) => {
  expect(dayWord(Date.parse(utc), THURSDAY_AFTERNOON)).toBe(expected);
});

it.each([
  // 23:30 BST on Saturday, before the change.
  ["2026-10-24T22:30Z", "tonight"],
  // 01:30 on Sunday, once in BST and again in GMT: both are the same night.
  ["2026-10-25T00:30Z", "tonight"],
  ["2026-10-25T01:30Z", "tonight"],
  // 23:30 GMT on Sunday, then 00:30 GMT on Monday.
  ["2026-10-25T23:30Z", "tomorrow"],
  ["2026-10-26T00:30Z", "tomorrow night"],
  ["2026-10-26T06:00Z", "Monday"],
])("calls %s %s across the October clock change", (utc, expected) => {
  expect(dayWord(Date.parse(utc), SATURDAY_BEFORE_CLOCK_CHANGE)).toBe(expected);
});

it("describes a window that has started as running from now", () => {
  const start = Date.parse("2026-11-19T15:00Z");
  expect(windowPhrase(start, start + 6 * HALF_HOUR_MS, THURSDAY_AFTERNOON + 60_000)).toBe("now until 18:00");
});

it("describes a later window by its day and clock times", () => {
  const start = Date.parse("2026-11-19T22:00Z");
  expect(windowPhrase(start, start + 6 * HALF_HOUR_MS, THURSDAY_AFTERNOON)).toBe("tonight, 22:00 to 01:00");
});

it("describes a window across the clock change in UK time", () => {
  const start = Date.parse("2026-10-24T23:00Z");
  expect(windowPhrase(start, start + 6 * HALF_HOUR_MS, SATURDAY_BEFORE_CLOCK_CHANGE)).toBe("tonight, 00:00 to 02:00");
});

it("heads a half hour with its day and clock times", () => {
  const start = Date.parse("2026-11-20T09:30Z");
  expect(halfHourPhrase(start, start + HALF_HOUR_MS, THURSDAY_AFTERNOON)).toBe("Tomorrow, 09:30 to 10:00");
});

it("says when the forecast was fetched, with its date", () => {
  expect(fetchedPhrase(Date.parse("2026-11-19T14:05:12Z"))).toBe("Forecast fetched 14:05, Thursday 19 November.");
});

it.each([
  [76, "76 minutes"],
  [119, "119 minutes"],
  [120, "2 hours"],
  [179, "2 hours"],
  [1_500, "25 hours"],
])("gives an age of %i minutes as %s", (minutes, expected) => {
  expect(ageText(minutes * 60_000)).toBe(expected);
});

it("names durations as nouns and adjectives", () => {
  expect([durationNoun(1), durationNoun(3)]).toEqual(["hour", "three hours"]);
  expect([durationAdjective(1), durationAdjective(4)]).toEqual(["one-hour", "four-hour"]);
});

it("agrees the verb with one hour or several", () => {
  expect(agree(1, "average")).toBe("averages");
  expect(agree(2, "average")).toBe("average");
});

it("rounds an intensity to the gram", () => {
  expect(grams(96.5)).toBe("97 g");
  expect(grams(231)).toBe("231 g");
});
