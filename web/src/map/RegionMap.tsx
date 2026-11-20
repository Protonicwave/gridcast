import { useId } from "react";
import { rampColour, rampGradient } from "../chartGeometry";
import type { Outlook } from "../forecastApi";
import { grams, slotPhrase } from "../time";
import { useMeasuredSize } from "../useMeasuredSize";
import { labelledRegionIds, type LabelRequest, type PlacedLabel, placeLabels } from "./labels";
import shapes from "./regionShapes.json";

const REGION_SHAPES: Readonly<Record<string, { readonly path: string; readonly labelAt: { readonly x: number; readonly y: number } } | undefined>> = shapes.regions;

/** Label text size on screen; the map's own units scale with the drawn width, so it is converted below. */
const LABEL_SIZE_PX = 12.5;
const LABEL_GAP_PX = 4;
const LABEL_HALO_PX = 3;

export interface RegionMapProps {
  readonly outlooks: ReadonlyMap<number, Outlook>;
  /** Index of the half hour to colour every region at. */
  readonly cursor: number;
  readonly selectedId: number | null;
  readonly nowMs: number;
  readonly onSelect: (regionId: number) => void;
}

/** Every region coloured by its forecast at the cursor's half hour, with the legend beneath. */
export function RegionMap({ outlooks, cursor, selectedId, nowMs, onSelect }: RegionMapProps) {
  const headingId = useId();
  const [measure, { widthPx, heightPx }] = useMeasuredSize();
  const { width: viewWidth, height: viewHeight } = shapes.viewBox;
  const first = outlooks.values().next().value;
  if (first === undefined) throw new RangeError("expected at least one outlook to draw");
  // Every outlook covers the same half hours, so the first one's length bounds the cursor for all.
  const slot = Math.min(Math.max(cursor, 0), first.intensities.length - 1);
  const valueById = new Map([...outlooks].map(([id, outlook]) => [id, outlook.intensities[slot] ?? 0] as const));
  // The map keeps its aspect ratio inside a height-limited box, so the drawn scale is the larger ratio.
  const unitsPerPx = widthPx > 0 && heightPx > 0 ? Math.max(viewWidth / widthPx, viewHeight / heightPx) : null;
  const labels = unitsPerPx === null ? [] : labelsFor(outlooks, valueById, selectedId, unitsPerPx);
  const startMs = first.firstSlotStartMs + slot * first.slotMs;

  return (
    <>
      <div className="map-head">
        <h2 id={headingId}>Across Great Britain, {slotPhrase(startMs, nowMs)}</h2>
      </div>
      <div className="map">
        <svg ref={measure} viewBox={`0 0 ${String(viewWidth)} ${String(viewHeight)}`} role="img" aria-labelledby={headingId}>
          <rect className="inset-frame" {...shapes.shetlandFrame} />
          <g>
            {[...outlooks.values()].map((outlook) => {
              const value = valueById.get(outlook.regionId) ?? 0;
              return (
                <path
                  key={outlook.regionId}
                  className={outlook.regionId === selectedId ? "region region--selected" : "region"}
                  d={shapeOf(outlook.regionId).path}
                  fill={rampColour(value)}
                  onClick={() => {
                    onSelect(outlook.regionId);
                  }}
                >
                  <title>{`${outlook.regionName}, ${grams(value)}`}</title>
                </path>
              );
            })}
          </g>
          <g>
            {labels.map((label) => (
              <MapLabel key={label.id} label={label} name={outlooks.get(label.id)?.regionName ?? ""} value={grams(valueById.get(label.id) ?? 0)} unitsPerPx={unitsPerPx ?? 1} />
            ))}
          </g>
        </svg>
      </div>
      <Legend />
    </>
  );
}

interface MapLabelProps {
  readonly label: PlacedLabel;
  readonly name: string;
  readonly value: string;
  readonly unitsPerPx: number;
}

function MapLabel({ label, name, value, unitsPerPx }: MapLabelProps) {
  return (
    <text x={label.x} y={label.y} textAnchor={label.anchor} fontSize={LABEL_SIZE_PX * unitsPerPx} strokeWidth={LABEL_HALO_PX * unitsPerPx}>
      <tspan className="label-name">{name}</tspan>
      <tspan className="label-value"> {value}</tspan>
    </text>
  );
}

function Legend() {
  return (
    <div className="legend" aria-hidden="true">
      <div className="legend__ramp" style={{ background: rampGradient() }} />
      <div className="legend__ticks">
        <span>0</span>
        <span>100</span>
        <span>200</span>
        <span>
          300+ g CO<sub>2</sub> per kWh
        </span>
      </div>
    </div>
  );
}

function labelsFor(outlooks: ReadonlyMap<number, Outlook>, valueById: ReadonlyMap<number, number>, selectedId: number | null, unitsPerPx: number): PlacedLabel[] {
  const requests = labelledRegionIds(valueById, selectedId).flatMap((id): LabelRequest[] => {
    const outlook = outlooks.get(id);
    const value = valueById.get(id);
    if (outlook === undefined || value === undefined) return [];
    const { x, y } = shapeOf(id).labelAt;
    return [{ id, text: `${outlook.regionName} ${grams(value)}`, x, y }];
  });
  return placeLabels(requests, { fontSize: LABEL_SIZE_PX * unitsPerPx, gap: LABEL_GAP_PX * unitsPerPx, view: shapes.viewBox });
}

function shapeOf(regionId: number) {
  const shape = REGION_SHAPES[String(regionId)];
  if (shape === undefined) throw new RangeError(`expected a shape for region ${String(regionId)}`);
  return shape;
}
