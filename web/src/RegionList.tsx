import { rampColour } from "./chartGeometry";
import { Spread } from "./Answer";
import { type DurationHours, type Outlook, windowsFor } from "./forecastApi";
import { capitalise, durationNoun, grams, slotPhrase } from "./time";

interface RegionListProps {
  readonly outlooks: ReadonlyMap<number, Outlook>;
  readonly hours: DurationHours;
  readonly selectedId: number | null;
  readonly nowMs: number;
  readonly onSelect: (regionId: number) => void;
}

/** Every region with its cleanest window and the forecast as a colour strip, cleanest first. */
export function RegionList({ outlooks, hours, selectedId, nowMs, onSelect }: RegionListProps) {
  const ordered = [...outlooks.values()]
    .map((outlook) => {
      const [shownHours, choice] = windowsFor(outlook, hours);
      return { outlook, choice, shownHours };
    })
    .sort((a, b) => a.choice.cleanest.meanGPerKwh - b.choice.cleanest.meanGPerKwh || a.outlook.regionName.localeCompare(b.outlook.regionName));
  return (
    <>
      <h2 id="list-heading">Every region's cleanest {durationNoun(hours)}</h2>
      <ol className="region-list" aria-labelledby="list-heading">
        {ordered.map(({ outlook, choice, shownHours }) => {
          const startMs = outlook.firstSlotStartMs + choice.cleanest.start * outlook.slotMs;
          return (
            <li key={outlook.regionId}>
              <button className="region-row" type="button" aria-pressed={outlook.regionId === selectedId} onClick={() => { onSelect(outlook.regionId); }}>
                <span className="region-row__name">{outlook.regionName}</span>
                <span className="region-row__when">
                  {choice.timingMatters ? (
                    `${capitalise(slotPhrase(startMs, nowMs))}, ${grams(choice.cleanest.meanGPerKwh)}`
                  ) : (
                    <>
                      Any time, <Spread choice={choice} />
                    </>
                  )}
                </span>
                <Strip outlook={outlook} hours={shownHours} bracket={choice.timingMatters ? choice.cleanest.start : null} />
              </button>
            </li>
          );
        })}
      </ol>
    </>
  );
}

function Strip({ outlook, hours, bracket }: { readonly outlook: Outlook; readonly hours: DurationHours; readonly bracket: number | null }) {
  const slotsInWindow = (hours * 60) / (outlook.slotMs / 60_000);
  return (
    <svg className="region-row__strip" viewBox={`0 0 ${String(outlook.intensities.length)} 1`} preserveAspectRatio="none" aria-hidden="true">
      {outlook.intensities.map((value, slot) => (
        <rect key={slot} x={slot} width={1.05} height={1} fill={rampColour(value)} />
      ))}
      {bracket !== null && (
        <rect x={bracket} width={slotsInWindow} height={1} fill="none" stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  );
}
