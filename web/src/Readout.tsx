import { halfHourPhrase } from "./time";

interface ReadoutProps {
  readonly startMs: number;
  readonly endMs: number;
  readonly nowMs: number;
  readonly gPerKwh: number;
}

/** The half hour under the chart's cursor. */
export function Readout({ startMs, endMs, nowMs, gPerKwh }: ReadoutProps) {
  return (
    <div className="readout">
      <h2>{halfHourPhrase(startMs, endMs, nowMs)}</h2>
      <p className="readout__value">
        {Math.round(gPerKwh)} g CO<sub>2</sub> per kWh
      </p>
    </div>
  );
}
