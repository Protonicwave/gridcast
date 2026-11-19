import { useEffect, useState } from "react";
import { Answer } from "./Answer";
import { Chart } from "./Chart";
import { DurationPicker } from "./DurationPicker";
import { DURATIONS_HOURS, type DurationHours, type DurationWindows, fetchOutlook, type Outlook, OutlookUnavailableError } from "./forecastApi";
import { Readout } from "./Readout";
import { ageText, fetchedPhrase } from "./time";

const LONDON_REGION_ID = 13;
const LONDON_NAME = "London";
const DEFAULT_HOURS: DurationHours = 3;
const HOUR_MS = 3_600_000;
/** A response faster than this shows no loading text, so a quick load does not flash. */
const LOADING_DELAY_MS = 200;
/** A page shown again after this long fetches a newer forecast. */
const REFRESH_AFTER_MS = 10 * 60_000;
/** Matches the collector's alert: no new forecast for this long means something is wrong. */
const STALE_AFTER_MS = 75 * 60_000;

type Load =
  | { readonly kind: "waiting" }
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly outlook: Outlook; readonly receivedAtMs: number }
  | { readonly kind: "unavailable" };

interface AppProps {
  /** Where the API is; empty for the page's own origin. */
  readonly apiBaseUrl: string;
  readonly now?: () => number;
}

export function App({ apiBaseUrl, now = Date.now }: AppProps) {
  const { load, retry } = useOutlook(apiBaseUrl, now);
  switch (load.kind) {
    case "waiting":
      return <div className="forecast" aria-busy="true" />;
    case "loading":
      return (
        <div className="forecast answer" aria-busy="true">
          <p className="answer__label">{LONDON_NAME}</p>
          <h1>Loading the forecast…</h1>
        </div>
      );
    case "unavailable":
      return <Unavailable onRetry={retry} />;
    case "ready":
      return <Forecast outlook={load.outlook} nowMs={load.receivedAtMs} />;
  }
}

function useOutlook(apiBaseUrl: string, now: () => number) {
  const [load, setLoad] = useState<Load>({ kind: "waiting" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const slow = setTimeout(() => {
      setLoad((current) => (current.kind === "waiting" ? { kind: "loading" } : current));
    }, LOADING_DELAY_MS);
    // Expected failures become the unavailable state; anything else is a bug, left to surface as an unhandled rejection.
    void fetchOutlook(apiBaseUrl, LONDON_REGION_ID, controller.signal)
      .then(
        (outlook) => {
          setLoad({ kind: "ready", outlook, receivedAtMs: now() });
        },
        (error: unknown) => {
          if (controller.signal.aborted) return;
          if (!(error instanceof OutlookUnavailableError)) throw error;
          console.error(error);
          setLoad({ kind: "unavailable" });
        },
      )
      .finally(() => {
        clearTimeout(slow);
      });
    return () => {
      controller.abort();
      clearTimeout(slow);
    };
  }, [apiBaseUrl, now, attempt]);

  useEffect(() => {
    if (load.kind !== "ready") return;
    const refreshIfOld = () => {
      if (document.visibilityState === "visible" && now() - load.receivedAtMs > REFRESH_AFTER_MS) setAttempt((n) => n + 1);
    };
    document.addEventListener("visibilitychange", refreshIfOld);
    return () => {
      document.removeEventListener("visibilitychange", refreshIfOld);
    };
  }, [load, now]);

  const retry = () => {
    setLoad({ kind: "waiting" });
    setAttempt((n) => n + 1);
  };
  return { load, retry };
}

function Forecast({ outlook, nowMs }: { readonly outlook: Outlook; readonly nowMs: number }) {
  const [selectedHours, setSelectedHours] = useState(hoursFromUrl);
  const [cursorChoice, setCursorChoice] = useState(0);
  const [hours, choice] = windowsFor(outlook, selectedHours);
  const cursor = Math.min(cursorChoice, outlook.intensities.length - 1);
  const cursorValue = outlook.intensities[cursor];
  if (cursorValue === undefined) throw new RangeError(`expected a cursor inside ${String(outlook.intensities.length)} half hours, got ${String(cursor)}`);
  const cursorStartMs = outlook.firstSlotStartMs + cursor * outlook.slotMs;
  const spanHours = Math.round((outlook.intensities.length * outlook.slotMs) / HOUR_MS);
  const ageMs = nowMs - outlook.fetchedAtMs;

  const selectHours = (next: DurationHours) => {
    setSelectedHours(next);
    writeHoursToUrl(next);
  };

  return (
    <div className="forecast">
      {ageMs > STALE_AFTER_MS && <StaleNotice age={ageText(ageMs)} />}
      <p className="freshness">{fetchedPhrase(outlook.fetchedAtMs)} NESO updates it every half hour.</p>
      <Answer outlook={outlook} hours={hours} choice={choice} spanHours={spanHours} nowMs={nowMs} />
      <DurationPicker selected={hours} available={outlook.windows} onSelect={selectHours} />
      <Chart
        outlook={outlook}
        heading={`Next ${String(spanHours)} hours in ${outlook.regionName}`}
        hours={hours}
        choice={choice}
        cursor={cursor}
        cursorValue={cursorValue}
        nowMs={nowMs}
        onCursorChange={setCursorChoice}
      />
      <Readout startMs={cursorStartMs} endMs={cursorStartMs + outlook.slotMs} nowMs={nowMs} gPerKwh={cursorValue} />
    </div>
  );
}

/** The chosen duration's windows, or the longest that fits when the forecast is too short for it. */
function windowsFor(outlook: Outlook, selected: DurationHours): readonly [DurationHours, DurationWindows] {
  const chosen = outlook.windows.get(selected);
  if (chosen !== undefined) return [selected, chosen];
  const longest = [...outlook.windows].at(-1);
  if (longest === undefined) throw new RangeError("expected an outlook with at least one duration's windows");
  return longest;
}

function hoursFromUrl(): DurationHours {
  const requested = Number(new URLSearchParams(window.location.search).get("hours"));
  return DURATIONS_HOURS.find((hours) => hours === requested) ?? DEFAULT_HOURS;
}

function writeHoursToUrl(hours: DurationHours) {
  const url = new URL(window.location.href);
  if (hours === DEFAULT_HOURS) url.searchParams.delete("hours");
  else url.searchParams.set("hours", String(hours));
  window.history.replaceState(null, "", url);
}

function StaleNotice({ age }: { readonly age: string }) {
  return (
    <div className="notice notice--warning" role="status">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
      <p>
        <strong>This forecast is {age} old.</strong> NESO normally updates it every half hour, and Gridcast has not received the
        latest one, so the times below may have moved.
      </p>
    </div>
  );
}

function Unavailable({ onRetry }: { readonly onRetry: () => void }) {
  return (
    <div className="forecast">
      <div className="notice notice--danger" role="alert">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v6M12 16.5v.5" />
        </svg>
        <p>
          <strong>Gridcast can't load the forecast right now.</strong> Nothing is shown rather than an old forecast that might send
          you to the wrong time. Try again in a few minutes.
        </p>
      </div>
      <button className="button button--quiet" type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
