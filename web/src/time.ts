/** UK clock times, durations and amounts in the words people in Britain use for them. */

import type { DurationHours } from "./forecastApi";

const TIME_ZONE = "Europe/London";
const DAY_MS = 86_400_000;
const MINUTE_MS = 60_000;
const EVENING_HOUR = 18;
const MORNING_HOUR = 6;
/** Below this an age reads better in minutes ("80 minutes") than in hours. */
const AGE_IN_HOURS_FROM_MINUTES = 120;

const timeFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const hourFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", hourCycle: "h23" });
const minuteFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, minute: "2-digit" });
const weekdayFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "long" });
const shortWeekdayFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "short" });
const dateKeyFormat = new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const longDateFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "long", day: "numeric", month: "long" });

/** "14:05" in UK time. */
export function clock(ms: number): string {
  return timeFormat.format(ms);
}

export function localHour(ms: number): number {
  return Number(hourFormat.format(ms));
}

export function isOnTheHour(ms: number): boolean {
  return Number(minuteFormat.format(ms)) === 0;
}

/** "Fri" in UK time. */
export function shortWeekday(ms: number): string {
  return shortWeekdayFormat.format(ms);
}

/** "today", "tonight", "tomorrow", "tomorrow night" or a weekday, as someone in Britain would say it at `nowMs`. */
export function dayWord(ms: number, nowMs: number): string {
  const days = Math.round((Date.parse(dateKeyFormat.format(ms)) - Date.parse(dateKeyFormat.format(nowMs))) / DAY_MS);
  const hour = localHour(ms);
  if (days === 0) return hour >= EVENING_HOUR ? "tonight" : "today";
  if (days === 1) return hour < MORNING_HOUR ? "tonight" : "tomorrow";
  if (days === 2 && hour < MORNING_HOUR) return "tomorrow night";
  return weekdayFormat.format(ms);
}

/** "now until 18:00" for a window under way at `nowMs`, otherwise "tonight, 22:00 to 01:00". */
export function windowPhrase(startMs: number, endMs: number, nowMs: number): string {
  if (startMs <= nowMs) return `now until ${clock(endMs)}`;
  return `${dayWord(startMs, nowMs)}, ${clock(startMs)} to ${clock(endMs)}`;
}

/** "now", or "tomorrow 02:00" for a half hour that has not begun at `nowMs`. */
export function slotPhrase(startMs: number, nowMs: number): string {
  return startMs <= nowMs ? "now" : `${dayWord(startMs, nowMs)} ${clock(startMs)}`;
}

/** "Tomorrow, 09:30 to 10:00". */
export function halfHourPhrase(startMs: number, endMs: number, nowMs: number): string {
  return `${capitalise(dayWord(startMs, nowMs))}, ${clock(startMs)} to ${clock(endMs)}`;
}

/** "Forecast fetched 14:05, Thursday 19 November." */
export function fetchedPhrase(fetchedMs: number): string {
  return `Forecast fetched ${clock(fetchedMs)}, ${longDateFormat.format(fetchedMs)}.`;
}

/** "80 minutes" or "2 hours", rounded down. */
export function ageText(ageMs: number): string {
  const minutes = Math.floor(ageMs / MINUTE_MS);
  if (minutes < AGE_IN_HOURS_FROM_MINUTES) return `${String(minutes)} minutes`;
  return `${String(Math.floor(minutes / 60))} hours`;
}

export function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const DURATION_NOUNS: Readonly<Record<DurationHours, string>> = { 1: "hour", 2: "two hours", 3: "three hours", 4: "four hours" };
const DURATION_ADJECTIVES: Readonly<Record<DurationHours, string>> = { 1: "one-hour", 2: "two-hour", 3: "three-hour", 4: "four-hour" };

/** "three hours", or "hour" for one, as in "the cleanest hour". */
export function durationNoun(hours: DurationHours): string {
  return DURATION_NOUNS[hours];
}

/** "three-hour", as in "every three-hour window". */
export function durationAdjective(hours: DurationHours): string {
  return DURATION_ADJECTIVES[hours];
}

/** The verb in agreement with "hour" or "hours": "averages" for one hour, "average" for more. */
export function agree(hours: DurationHours, verb: string): string {
  return hours === 1 ? `${verb}s` : verb;
}

/** "96 g", rounded to the gram. */
export function grams(gPerKwh: number): string {
  return `${String(Math.round(gPerKwh))} g`;
}
