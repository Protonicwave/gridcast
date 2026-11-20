import { type KeyboardEvent, type PointerEvent, useId } from "react";
import { type ChartScales, chartScales, hourTicks, rampColour, stepPath, valueTicks } from "./chartGeometry";
import type { DurationHours, DurationWindows, Outlook } from "./forecastApi";
import { clock, dayWord, durationNoun } from "./time";
import { useMeasuredSize } from "./useMeasuredSize";

/** Keeps the window's label inside the plot when the window sits at either end. */
const WINDOW_LABEL_HALF_WIDTH_PX = 40;
/** The "Now" label is dropped when the window's label would sit on top of it. */
const NOW_LABEL_CLEARANCE_PX = 48;
const PAGE_STEP_SLOTS = 12;

interface ChartProps {
  readonly outlook: Outlook;
  readonly heading: string;
  readonly hours: DurationHours;
  readonly choice: DurationWindows;
  readonly cursor: number;
  readonly cursorValue: number;
  readonly nowMs: number;
  readonly onCursorChange: (slot: number) => void;
}

/** The forecast as a step line with the cleanest window shaded; a slider over its half hours. */
export function Chart({ outlook, heading, hours, choice, cursor, cursorValue, nowMs, onCursorChange }: ChartProps) {
  const headingId = useId();
  const [measure, { widthPx: measuredWidthPx }] = useMeasuredSize();
  const slotCount = outlook.intensities.length;
  const scales = chartScales(measuredWidthPx, slotCount, Math.max(...outlook.intensities));
  const cursorStartMs = outlook.firstSlotStartMs + cursor * outlook.slotMs;

  const moveTo = (slot: number) => {
    onCursorChange(Math.min(Math.max(slot, 0), slotCount - 1));
  };
  const onKeyDown = (event: KeyboardEvent) => {
    const target = keyTarget(event.key, cursor, slotCount);
    if (target === null) return;
    event.preventDefault();
    moveTo(target);
  };
  const followPointer = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    moveTo(scales.slotAt(((event.clientX - box.left) / box.width) * scales.width));
  };

  return (
    <>
      <ChartHead headingId={headingId} heading={heading} windowKey={choice.timingMatters ? `Cleanest ${durationNoun(hours)}` : null} />
      <div
        ref={measure}
        className="chart"
        tabIndex={0}
        role="slider"
        aria-labelledby={headingId}
        aria-valuemin={0}
        aria-valuemax={slotCount - 1}
        aria-valuenow={cursor}
        aria-valuetext={`${dayWord(cursorStartMs, nowMs)} ${clock(cursorStartMs)}, ${String(Math.round(cursorValue))} grams per kilowatt hour`}
        onKeyDown={onKeyDown}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          followPointer(event);
        }}
        onPointerMove={(event) => {
          if (event.pointerType === "mouse" || event.currentTarget.hasPointerCapture(event.pointerId)) followPointer(event);
        }}
      >
        <svg viewBox={`0 0 ${String(scales.width)} ${String(scales.height)}`} width={scales.width} height={scales.height} aria-hidden="true">
          <Axes outlook={outlook} scales={scales} />
          <WindowBand outlook={outlook} scales={scales} hours={hours} choice={choice} nowMs={nowMs} />
          <path className="series" d={stepPath(outlook.intensities, scales.x, scales.y)} />
          <Strip intensities={outlook.intensities} scales={scales} />
          <Cursor scales={scales} slot={cursor} gPerKwh={cursorValue} />
        </svg>
      </div>
    </>
  );
}

function ChartHead({ headingId, heading, windowKey }: { readonly headingId: string; readonly heading: string; readonly windowKey: string | null }) {
  return (
    <div className="chart-head">
      <h2 id={headingId}>{heading}</h2>
      <ul className="key">
        <li>
          <span className="key__swatch key__swatch--line" />
          <span>
            NESO forecast, g CO<sub>2</sub> per kWh
          </span>
        </li>
        {windowKey !== null && (
          <li>
            <span className="key__swatch key__swatch--window" />
            {windowKey}
          </li>
        )}
      </ul>
    </div>
  );
}

function Cursor({ scales, slot, gPerKwh }: { readonly scales: ChartScales; readonly slot: number; readonly gPerKwh: number }) {
  const centre = scales.x(slot + 0.5);
  return (
    <>
      <line className="cursor-line" x1={centre} x2={centre} y1={scales.margin.top} y2={scales.plotBottom} />
      <circle className="cursor-dot" r={4.5} cx={centre} cy={scales.y(gPerKwh)} />
    </>
  );
}

function keyTarget(key: string, cursor: number, slotCount: number): number | null {
  switch (key) {
    case "ArrowLeft":
      return cursor - 1;
    case "ArrowRight":
      return cursor + 1;
    case "PageUp":
      return cursor - PAGE_STEP_SLOTS;
    case "PageDown":
      return cursor + PAGE_STEP_SLOTS;
    case "Home":
      return 0;
    case "End":
      return slotCount - 1;
    default:
      return null;
  }
}

function Axes({ outlook, scales }: { readonly outlook: Outlook; readonly scales: ChartScales }) {
  const { margin, plotBottom, width, x, y } = scales;
  return (
    <>
      {valueTicks(scales.top).map((value) => (
        <g key={`value-${String(value)}`}>
          <line className="gridline" x1={margin.left} x2={width - margin.right} y1={y(value)} y2={y(value)} />
          <text x={margin.left - 6} y={y(value) + 4} textAnchor="end">
            {value}
          </text>
        </g>
      ))}
      {hourTicks(outlook.firstSlotStartMs, outlook.intensities.length, outlook.slotMs).map((tick) => (
        <g key={`hour-${String(tick.slot)}`}>
          {tick.isDayStart && <line className="dayline" x1={x(tick.slot)} x2={x(tick.slot)} y1={margin.top} y2={plotBottom + 14} />}
          <text x={x(tick.slot)} y={plotBottom + 30} textAnchor="middle" className={tick.isDayStart ? "tick-day" : undefined}>
            {tick.label}
          </text>
        </g>
      ))}
    </>
  );
}

interface WindowBandProps {
  readonly outlook: Outlook;
  readonly scales: ChartScales;
  readonly hours: DurationHours;
  readonly choice: DurationWindows;
  readonly nowMs: number;
}

function WindowBand({ outlook, scales, hours, choice, nowMs }: WindowBandProps) {
  const { margin, plotBottom, width, x } = scales;
  const slots = (hours * 3_600_000) / outlook.slotMs;
  const left = x(choice.cleanest.start);
  const right = x(choice.cleanest.start + slots);
  const nowSlot = Math.min(Math.max((nowMs - outlook.firstSlotStartMs) / outlook.slotMs, 0), outlook.intensities.length);
  const nowX = x(nowSlot);
  const labelX = Math.min(Math.max((left + right) / 2, margin.left + WINDOW_LABEL_HALF_WIDTH_PX), width - margin.right - WINDOW_LABEL_HALF_WIDTH_PX);
  return (
    <>
      {choice.timingMatters && (
        <>
          <rect className="window-band" x={left} y={margin.top} width={right - left} height={plotBottom - margin.top} />
          <line className="window-edge" x1={left} x2={right} y1={margin.top} y2={margin.top} />
          <text className="window-label halo" x={labelX} y={margin.top - 8} textAnchor="middle">
            Cleanest {hours} h
          </text>
        </>
      )}
      <line className="now-line" x1={nowX} x2={nowX} y1={margin.top} y2={plotBottom} />
      {(!choice.timingMatters || left - nowX > NOW_LABEL_CLEARANCE_PX) && (
        <text className="now-label halo" x={nowX} y={margin.top - 8} textAnchor="start">
          Now
        </text>
      )}
    </>
  );
}

function Strip({ intensities, scales }: { readonly intensities: readonly number[]; readonly scales: ChartScales }) {
  const cellWidth = scales.x(1) - scales.x(0);
  return (
    <>
      {intensities.map((value, slot) => (
        <rect
          // The strip is redrawn whole whenever the series changes, so the slot is a stable key.
          key={slot}
          x={(scales.x(slot) - 0.2).toFixed(1)}
          y={scales.plotBottom + 4}
          width={(cellWidth + 0.4).toFixed(1)}
          height={8}
          fill={rampColour(value)}
          shapeRendering="crispEdges"
        />
      ))}
    </>
  );
}
