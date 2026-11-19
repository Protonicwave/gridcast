import { Fragment } from "react";
import { DURATIONS_HOURS, type DurationHours } from "./forecastApi";

interface DurationPickerProps {
  readonly selected: DurationHours;
  /** Durations that fit in what remains of the forecast; the others are shown disabled. */
  readonly available: ReadonlyMap<DurationHours, unknown>;
  readonly onSelect: (hours: DurationHours) => void;
}

export function DurationPicker({ selected, available, onSelect }: DurationPickerProps) {
  return (
    <fieldset className="length-row">
      <legend>Window length</legend>
      <div className="segmented">
        {DURATIONS_HOURS.map((hours) => (
          <Fragment key={hours}>
            <input
              type="radio"
              name="hours"
              id={`hours-${String(hours)}`}
              value={hours}
              checked={hours === selected}
              disabled={!available.has(hours)}
              onChange={() => {
                onSelect(hours);
              }}
            />
            <label htmlFor={`hours-${String(hours)}`}>{hours} h</label>
          </Fragment>
        ))}
      </div>
    </fieldset>
  );
}
