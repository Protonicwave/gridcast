import type { DurationHours, DurationWindows, ForecastWindow, Outlook } from "./forecastApi";
import { agree, capitalise, durationAdjective, durationNoun, grams, windowPhrase } from "./time";

const HOUR_MS = 3_600_000;

interface AnswerProps {
  readonly outlook: Outlook;
  readonly hours: DurationHours;
  readonly choice: DurationWindows;
  readonly spanHours: number;
  readonly nowMs: number;
}

/** The page's answer: when the cleanest window is, or that timing makes little difference. */
export function Answer({ outlook, hours, choice, spanHours, nowMs }: AnswerProps) {
  const noun = durationNoun(hours);
  const phrase = (window: ForecastWindow) => {
    const startMs = outlook.firstSlotStartMs + window.start * outlook.slotMs;
    return windowPhrase(startMs, startMs + hours * HOUR_MS, nowMs);
  };
  if (!choice.timingMatters) {
    return (
      <div className="answer" aria-live="polite">
        <p className="answer__label">Next {spanHours} hours in {outlook.regionName}</p>
        <h1>Any time works about as well</h1>
        <p className="answer__detail">
          Every {durationAdjective(hours)} window averages <Spread choice={choice} /> of CO<sub>2</sub> per kWh, so there
          is little to gain by waiting.
        </p>
      </div>
    );
  }
  return (
    <div className="answer" aria-live="polite">
      <p className="answer__label">
        Cleanest {noun} in {outlook.regionName}
      </p>
      <h1>{capitalise(phrase(choice.cleanest))}</h1>
      <p className="answer__detail">
        About <strong className="nowrap">{grams(choice.cleanest.meanGPerKwh)}</strong> of CO<sub>2</sub> per kWh. The
        dirtiest {noun}, {phrase(choice.dirtiest)}, {agree(hours, "average")}{" "}
        <span className="nowrap">{grams(choice.dirtiest.meanGPerKwh)}</span>.
      </p>
    </div>
  );
}

function Spread({ choice }: { readonly choice: DurationWindows }) {
  const low = grams(choice.cleanest.meanGPerKwh);
  const high = grams(choice.dirtiest.meanGPerKwh);
  if (low === high) {
    return (
      <>
        about <span className="nowrap">{low}</span>
      </>
    );
  }
  return (
    <>
      between <span className="nowrap">{low}</span> and <span className="nowrap">{high}</span>
    </>
  );
}
