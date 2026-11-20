import { type ReactNode, useEffect, useState } from "react";
import { Answer } from "./Answer";
import { Chart } from "./Chart";
import { DurationPicker } from "./DurationPicker";
import { type DurationHours, fetchOutlooks, type Outlook, OutlookUnavailableError, windowsFor } from "./forecastApi";
import { PostcodeForm } from "./PostcodeForm";
import { Readout } from "./Readout";
import { MapSlot } from "./map/MapSlot";
import { RegionList } from "./RegionList";
import { ageText, fetchedPhrase } from "./time";
import { parseUrlState, type UrlState, urlWithState } from "./urlState";

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
  | { readonly kind: "ready"; readonly outlooks: ReadonlyMap<number, Outlook>; readonly receivedAtMs: number }
  | { readonly kind: "unavailable" };

interface AppProps {
  /** Where the API is; empty for the page's own origin. */
  readonly apiBaseUrl: string;
  readonly now?: () => number;
}

export function App({ apiBaseUrl, now = Date.now }: AppProps) {
  const { load, retry } = useOutlooks(apiBaseUrl, now);
  switch (load.kind) {
    case "waiting":
      return <div className="forecast" aria-busy="true" />;
    case "loading":
      return (
        <div className="forecast answer" aria-busy="true">
          <p className="answer__label">Great Britain</p>
          <h1>Loading the forecast…</h1>
        </div>
      );
    case "unavailable":
      return <Unavailable onRetry={retry} />;
    case "ready":
      return <Regions outlooks={load.outlooks} nowMs={load.receivedAtMs} />;
  }
}

interface RegionsProps {
  readonly outlooks: ReadonlyMap<number, Outlook>;
  readonly nowMs: number;
}

/** The chosen region's forecast, or the prompt before one is chosen, beside the list of every region. */
function Regions({ outlooks, nowMs }: RegionsProps) {
  const [urlState, setUrlState] = useState(() => parseUrlState(window.location.search));
  const choose = (next: UrlState) => {
    setUrlState(next);
    window.history.replaceState(null, "", urlWithState(window.location.href, next));
  };
  const selectRegion = (regionId: number) => {
    choose({ ...urlState, regionId });
  };
  const [cursor, setCursor] = useState(0);
  const region = urlState.regionId === null ? undefined : outlooks.get(urlState.regionId);
  const form = <PostcodeForm onRegion={selectRegion} />;
  return (
    <div className="forecast-layout">
      <div className="forecast-main">
        {region === undefined ? (
          <Prompt form={form} />
        ) : (
          <Forecast
            key={region.regionId}
            outlook={region}
            cursor={cursor}
            onCursorChange={setCursor}
            hours={urlState.hours}
            nowMs={nowMs}
            form={form}
            onSelectHours={(hours) => {
              choose({ ...urlState, hours });
            }}
          />
        )}
      </div>
      <aside className="forecast-aside">
        <MapSlot outlooks={outlooks} cursor={cursor} selectedId={region?.regionId ?? null} nowMs={nowMs} onSelect={selectRegion} />
        <RegionList outlooks={outlooks} hours={urlState.hours} selectedId={region?.regionId ?? null} nowMs={nowMs} onSelect={selectRegion} />
      </aside>
    </div>
  );
}

function useOutlooks(apiBaseUrl: string, now: () => number) {
  const [load, setLoad] = useState<Load>({ kind: "waiting" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const slow = setTimeout(() => {
      setLoad((current) => (current.kind === "waiting" ? { kind: "loading" } : current));
    }, LOADING_DELAY_MS);
    // Expected failures become the unavailable state; anything else is a bug, left to surface as an unhandled rejection.
    void fetchOutlooks(apiBaseUrl, controller.signal)
      .then(
        (outlooks) => {
          setLoad({ kind: "ready", outlooks, receivedAtMs: now() });
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

interface ForecastProps {
  readonly outlook: Outlook;
  readonly hours: DurationHours;
  readonly nowMs: number;
  /** The half hour under the cursor, shared with the map. */
  readonly cursor: number;
  readonly onCursorChange: (slot: number) => void;
  /** The postcode form, shown between the answer and the detail. */
  readonly form: ReactNode;
  readonly onSelectHours: (hours: DurationHours) => void;
}

function Forecast({ outlook, hours: selectedHours, nowMs, cursor: requestedCursor, onCursorChange, form, onSelectHours }: ForecastProps) {
  const [hours, choice] = windowsFor(outlook, selectedHours);
  const cursor = Math.min(requestedCursor, outlook.intensities.length - 1);
  const cursorValue = outlook.intensities[cursor];
  if (cursorValue === undefined) throw new RangeError(`expected a cursor inside ${String(outlook.intensities.length)} half hours, got ${String(cursor)}`);
  const cursorStartMs = outlook.firstSlotStartMs + cursor * outlook.slotMs;
  const spanHours = Math.round((outlook.intensities.length * outlook.slotMs) / HOUR_MS);
  const ageMs = nowMs - outlook.fetchedAtMs;

  return (
    <>
      {ageMs > STALE_AFTER_MS && <StaleNotice age={ageText(ageMs)} />}
      <p className="freshness">{fetchedPhrase(outlook.fetchedAtMs)} NESO updates it every half hour.</p>
      <Answer outlook={outlook} hours={hours} choice={choice} spanHours={spanHours} nowMs={nowMs} />
      {form}
      <DurationPicker selected={hours} available={outlook.windows} onSelect={onSelectHours} />
      <Chart
        outlook={outlook}
        heading={`Next ${String(spanHours)} hours in ${outlook.regionName}`}
        hours={hours}
        choice={choice}
        cursor={cursor}
        cursorValue={cursorValue}
        nowMs={nowMs}
        onCursorChange={onCursorChange}
      />
      <p className="chart-hint">Drag along the chart, or use the arrow keys, to see any half hour on the map.</p>
      <Readout startMs={cursorStartMs} endMs={cursorStartMs + outlook.slotMs} nowMs={nowMs} gPerKwh={cursorValue} />
    </>
  );
}

function Prompt({ form }: { readonly form: ReactNode }) {
  return (
    <>
      <div className="answer">
        <h1>When is your electricity cleanest?</h1>
        <p className="answer__detail">Enter a postcode, or pick a region on the map or from the list, to see the cleanest time to use electricity there in the next 48 hours.</p>
      </div>
      {form}
    </>
  );
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
