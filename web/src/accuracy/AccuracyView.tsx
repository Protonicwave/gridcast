import { useEffect, useId, useState } from "react";
import { AccuracyUnavailableError, type BandAccuracy, type Estimate, fetchAccuracy, type Interval, type NationalAccuracy } from "./accuracyApi";
import { PILOT } from "./pilot";

/** The week of the 12-week plan in which H2 is decided; the running figures stop being provisional then. */
const H2_DUE_WEEK = 6;
/** Fewest usable days for which the API reports an interval. */
const MIN_DAYS_FOR_INTERVAL = 7;

type Load =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly accuracy: NationalAccuracy }
  | { readonly kind: "unavailable" };

interface AccuracyViewProps {
  /** Where the API is; empty for the page's own origin. */
  readonly apiBaseUrl: string;
}

/** How good NESO's national forecast is: the running figures by horizon, the four tests, and the 2025 pilot. */
export function AccuracyView({ apiBaseUrl }: AccuracyViewProps) {
  const { load, retry } = useAccuracy(apiBaseUrl);
  return (
    <div className="accuracy">
      <div className="prose">
        <h1>How good is the forecast?</h1>
        <p>
          A forecast is only useful if you know how far to trust it. NESO publishes no accuracy figure for its own carbon forecast, so
          Gridcast keeps every forecast as it was issued and checks it against what happened. This page grows as that record does.
        </p>
      </div>
      <HorizonSection load={load} onRetry={retry} />
      <HypothesesSection />
      <PilotSection />
      <div className="section prose">
        <h2>What these numbers cannot tell you</h2>
        <p>
          There is no published actual for each region, only for Great Britain as a whole. Regional forecasts are checked against NESO's
          latest estimate for the half hour, which is itself a model, so the verdicts here rest on the national comparison.
        </p>
        <p>
          The figures are for average carbon intensity. Using electricity at a cleaner time adds load that the grid meets from whichever
          plant is on the margin, which can be dirtier than the average, so a cleaner window does not mean an equal cut in your emissions.
        </p>
        <p>
          The first verdicts will come from autumn and winter. Solar power moves the cleanest hours towards midday in summer, so they
          should be repeated after a full year.
        </p>
      </div>
    </div>
  );
}

function useAccuracy(apiBaseUrl: string) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    // Expected failures become the unavailable state; anything else is a bug, left to surface as an unhandled rejection.
    void fetchAccuracy(apiBaseUrl, controller.signal).then(
      (accuracy) => {
        setLoad({ kind: "ready", accuracy });
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        if (!(error instanceof AccuracyUnavailableError)) throw error;
        console.error(error);
        setLoad({ kind: "unavailable" });
      },
    );
    return () => {
      controller.abort();
    };
  }, [apiBaseUrl, attempt]);

  const retry = () => {
    setLoad({ kind: "loading" });
    setAttempt((n) => n + 1);
  };
  return { load, retry };
}

function HorizonSection({ load, onRetry }: { readonly load: Load; readonly onRetry: () => void }) {
  return (
    <div className="section">
      <h2>Error by how far ahead the forecast looks</h2>
      <p className="prose">
        Average error of NESO's national forecast, in g CO<sub>2</sub> per kWh, against what the grid then did. Each forecast is placed by
        how long before the half hour Gridcast fetched it, and each figure carries its 95% interval.
      </p>
      {load.kind === "ready" && <HorizonResults accuracy={load.accuracy} />}
      {load.kind === "loading" && (
        <p className="muted" aria-busy="true">
          Loading the measured figures…
        </p>
      )}
      {load.kind === "unavailable" && (
        <div className="notice notice--danger" role="alert">
          <p>
            <strong>The measured figures can't be loaded right now.</strong> The rest of this page does not depend on them.
          </p>
          <button className="button button--quiet" type="button" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

function HorizonResults({ accuracy }: { readonly accuracy: NationalAccuracy }) {
  return (
    <>
      <div className="table-scroll">
        <table className="horizon">
          <caption className="visually-hidden">Forecast error by horizon, with 95% intervals</caption>
          <thead>
            <tr>
              <th scope="col">Forecast</th>
              {accuracy.bands.map((band) => (
                <th scope="col" key={band.fromHours}>
                  {bandHeading(band)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">NESO</th>
              {accuracy.bands.map((band) => (
                <td key={band.fromHours}>
                  <Figure estimate={band.estimate} />
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Gridcast</th>
              {accuracy.bands.map((band) => (
                <td className="horizon__later" key={band.fromHours}>
                  From week 8
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <H2Reading accuracy={accuracy} />
      <DaysUsed accuracy={accuracy} />
    </>
  );
}

function bandHeading(band: BandAccuracy): string {
  return band.fromHours === 1 ? `${String(band.fromHours)} to ${String(band.toHours)} h ahead` : `${String(band.fromHours)} to ${String(band.toHours)} h`;
}

function Figure({ estimate }: { readonly estimate: Estimate }) {
  if (estimate.maeGPerKwh === null) return <span className="muted">Not enough days yet</span>;
  return (
    <>
      <span className="horizon__value">{oneDecimal(estimate.maeGPerKwh)} g</span>
      {estimate.interval !== null && (
        <span className="horizon__interval">
          {oneDecimal(estimate.interval.low)} to {oneDecimal(estimate.interval.high)}
        </span>
      )}
    </>
  );
}

/** H2 so far, in words, from the difference between the 24 to 48 hour band's error and the 1 to 6 hour band's. */
function H2Reading({ accuracy }: { readonly accuracy: NationalAccuracy }) {
  const { maeGPerKwh, interval } = accuracy.difference;
  const dayCount = accuracy.usableDays.length;
  if (maeGPerKwh === null || interval === null) {
    return (
      <p className="prose reading">
        <strong>H2 so far:</strong> {dayCount === 0 ? "no full day has been measured yet." : `${String(dayCount)} full ${plural(dayCount, "day")} measured.`} The
        interval, and so any reading of H2, needs {String(MIN_DAYS_FOR_INTERVAL)}.
      </p>
    );
  }
  return (
    <p className="prose reading">
      <strong>H2 so far:</strong> {readDifference(maeGPerKwh, interval)} The verdict comes in week {String(H2_DUE_WEEK)}, on the days
      measured by then.
    </p>
  );
}

function readDifference(difference: number, interval: Interval): string {
  const gap = `${oneDecimal(Math.abs(difference))} g`;
  const range = `${oneDecimal(interval.low)} to ${oneDecimal(interval.high)} g`;
  if (interval.low > 0) {
    return `Forecasts fetched 24 to 48 hours ahead have missed by ${gap} more than those fetched 1 to 6 hours ahead. The 95% interval, ${range}, is wholly above zero, which is the pattern H2 predicts.`;
  }
  if (interval.high < 0) {
    return `Forecasts fetched 24 to 48 hours ahead have missed by ${gap} less than those fetched 1 to 6 hours ahead. The 95% interval, ${range}, is wholly below zero, the opposite of what H2 predicts.`;
  }
  const direction = difference >= 0 ? "more" : "less";
  return `Forecasts fetched 24 to 48 hours ahead have missed by ${gap} ${direction} than those fetched 1 to 6 hours ahead, but the 95% interval, ${range}, includes zero, so the two cannot yet be told apart.`;
}

function DaysUsed({ accuracy }: { readonly accuracy: NationalAccuracy }) {
  const used = accuracy.usableDays.length;
  const left = accuracy.excludedDays.length;
  return (
    <details className="days">
      <summary>
        {String(used)} full {plural(used, "day")} measured, {String(left)} left out
      </summary>
      <p className="muted small">
        A day counts when every half hour of it has an actual and each horizon has most of its forecasts. Figures cover the days up to
        but not including {dayText(accuracy.until)}.
      </p>
      {left > 0 && (
        <ul className="days__excluded">
          {accuracy.excludedDays.map((excluded) => (
            <li key={excluded.day}>
              <span className="nowrap">{dayText(excluded.day)}</span>: {excluded.reason}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

const HYPOTHESES = [
  {
    id: "H1",
    claim: "Gridcast's weather-driven model beats simple baselines.",
    disproof: "Disproved if repeating yesterday, or the average of the last four weeks, is as accurate at any forecast horizon.",
    status: "Not yet tested",
    due: "Due in week 8 of 12.",
  },
  {
    id: "H2",
    claim: "NESO's forecast gets worse the further ahead it looks.",
    disproof: "Disproved if its error 24 to 48 hours ahead is not clearly larger than 1 to 6 hours ahead.",
    status: "Being measured",
    due: `Running figures above. Verdict due in week ${String(H2_DUE_WEEK)} of 12.`,
  },
  {
    id: "H3",
    claim: "A day or two ahead, Gridcast is as accurate as NESO.",
    disproof: "Disproved if NESO's error is clearly lower 24 to 48 hours ahead.",
    status: "Not yet tested",
    due: "Due in week 9 of 12.",
  },
  {
    id: "H4",
    claim: "The recommended window is close to the best one.",
    disproof: "Disproved if, on fewer than 70 in 100 days, the three hours recommended at 18:00 the evening before come within 10% of that day's cleanest three hours.",
    status: "Not yet tested",
    due: "Due in week 10 of 12.",
  },
] as const;

function HypothesesSection() {
  return (
    <div className="section">
      <h2>Four tests, fixed before the data</h2>
      <p className="prose">Each claim was written down with the result that would disprove it before any of the data that tests it existed.</p>
      <ol className="hypotheses">
        {HYPOTHESES.map((hypothesis) => (
          <li key={hypothesis.id}>
            <span className="hypotheses__id">{hypothesis.id}</span>
            <span className="hypotheses__claim">{hypothesis.claim}</span>
            <span className="muted">{hypothesis.disproof}</span>
            <span className="hypotheses__status">
              <span className="status-pending">{hypothesis.status}</span>
              {hypothesis.due}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PilotSection() {
  const headingId = useId();
  return (
    <div className="section">
      <h2>What the 2025 pilot found</h2>
      <p className="prose">A pilot compared NESO's national forecast with its national actual for every half hour of 2025.</p>
      <dl className="figures">
        <div>
          <dt>{oneDecimal(PILOT.maeGPerKwh)} g</dt>
          <dd>
            Average error per kWh over {PILOT.halfHours.toLocaleString("en-GB")} half hours. The 95% interval is{" "}
            {oneDecimal(PILOT.intervalGPerKwh.low)} to {oneDecimal(PILOT.intervalGPerKwh.high)} g.
          </dd>
        </div>
        <div>
          <dt>Under {String(PILOT.p95AbsoluteErrorG)} g</dt>
          <dd>The error in 95 of every 100 half hours.</dd>
        </div>
        <div>
          <dt>{String(Math.round(PILOT.shareWithinThreshold * 100))} in 100 days</dt>
          <dd>
            The forecast's cleanest {String(PILOT.windowHours)} hours came within {String(Math.round(PILOT.regretThreshold * 100))}% of the day's actual best.
            It picked exactly the best ones on {String(Math.round(PILOT.shareExactBest * 100))} days in 100.
          </dd>
        </div>
      </dl>
      <div className="caveat">
        <p>
          <strong>These figures probably flatter the forecast.</strong> The API keeps one forecast for each past half hour and does not say
          when it was made, so most of these errors come from forecasts made close to the time. Gridcast's own archive records when every
          forecast was issued, which is what makes the error a day or two ahead measurable.
        </p>
      </div>
      <h3 id={headingId}>Average error by hour of day, 2025</h3>
      <p className="prose muted small">
        Mean absolute error of NESO's national forecast, in g CO<sub>2</sub> per kWh, by hour in UTC. The dashed line is the year's average.
      </p>
      <HourChart headingId={headingId} />
    </div>
  );
}

const CHART = { width: 760, height: 220, left: 30, right: 8, top: 12, bottom: 28, gridStepG: 5, labelEveryHours: 3 } as const;

function HourChart({ headingId }: { readonly headingId: string }) {
  const values = PILOT.maeByHourUtc;
  const top = Math.max(CHART.gridStepG, Math.ceil(Math.max(...values) / CHART.gridStepG) * CHART.gridStepG);
  const band = (CHART.width - CHART.left - CHART.right) / values.length;
  const y = (value: number) => CHART.top + (1 - value / top) * (CHART.height - CHART.top - CHART.bottom);
  const gridValues = Array.from({ length: top / CHART.gridStepG + 1 }, (_, i) => i * CHART.gridStepG);
  return (
    <div className="hour-chart">
      <svg viewBox={`0 0 ${String(CHART.width)} ${String(CHART.height)}`} role="img" aria-labelledby={headingId}>
        {gridValues.map((value) => (
          <g key={value}>
            <line x1={CHART.left} x2={CHART.width - CHART.right} y1={y(value)} y2={y(value)} className="gridline" />
            <text x={CHART.left - 6} y={y(value) + 4} textAnchor="end">
              {value}
            </text>
          </g>
        ))}
        {values.map((value, hour) => {
          const x = CHART.left + hour * band;
          return (
            <g key={hour}>
              <rect className="bar" x={x + 2} y={y(value)} width={band - 4} height={y(0) - y(value)}>
                <title>{`${String(hour).padStart(2, "0")}:00 UTC: ${oneDecimal(value)} g`}</title>
              </rect>
              {hour % CHART.labelEveryHours === 0 && (
                <text x={x + band / 2} y={CHART.height - 8} textAnchor="middle">
                  {String(hour).padStart(2, "0")}
                </text>
              )}
            </g>
          );
        })}
        <line className="mean-line" x1={CHART.left} x2={CHART.width - CHART.right} y1={y(PILOT.maeGPerKwh)} y2={y(PILOT.maeGPerKwh)} />
      </svg>
    </div>
  );
}

function oneDecimal(value: number): string {
  return value.toFixed(1);
}

function plural(count: number, noun: string): string {
  return count === 1 ? noun : `${noun}s`;
}

/** "20 Nov" for a UTC date such as 2026-11-20. */
function dayText(day: string): string {
  return new Date(`${day}T00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}
