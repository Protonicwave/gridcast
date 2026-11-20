/** Which regions the map names, and where each name sits. Pure, so it needs no layout engine. */

/** Roughly the average width of a glyph of the page's text face, as a fraction of its font size. */
const GLYPH_WIDTH_EM = 0.56;
const ASCENT_EM = 0.8;
const DESCENT_EM = 0.25;
/** Puts the middle of a label's capitals on its anchor when the label sits beside it. */
const CENTRE_BASELINE_EM = 0.35;

const SIDES = [
  { dx: 1, dy: 0, anchor: "start" },
  { dx: -1, dy: 0, anchor: "end" },
  { dx: 0, dy: -1, anchor: "middle" },
  { dx: 0, dy: 1, anchor: "middle" },
] as const;

export interface LabelRequest {
  readonly id: number;
  readonly text: string;
  /** The point to label, in map units. */
  readonly x: number;
  readonly y: number;
}

export interface LabelLayout {
  /** In map units. */
  readonly fontSize: number;
  /** Space between the anchor and the label, in map units. */
  readonly gap: number;
  readonly view: { readonly width: number; readonly height: number };
}

export interface PlacedLabel {
  readonly id: number;
  readonly text: string;
  /** The text's anchor point: its left, right or middle edge, on the baseline. */
  readonly x: number;
  readonly y: number;
  readonly anchor: (typeof SIDES)[number]["anchor"];
}

interface Box {
  readonly left: number;
  readonly right: number;
  readonly top: number;
  readonly bottom: number;
}

export function estimateLabelWidth(text: string, fontSize: number): number {
  return text.length * fontSize * GLYPH_WIDTH_EM;
}

/** The selected region, then the cleanest and the dirtiest, each once. Ties go to the lower region number. */
export function labelledRegionIds(valueById: ReadonlyMap<number, number>, selectedId: number | null): number[] {
  const ordered = [...valueById].sort(([idA, a], [idB, b]) => a - b || idA - idB);
  const wanted = [selectedId, ordered[0]?.[0], ordered.at(-1)?.[0]];
  return wanted.filter((id, index): id is number => id !== null && id !== undefined && valueById.has(id) && wanted.indexOf(id) === index);
}

/**
 * Puts each label on the first side of its anchor (right, left, above, below) where it stays inside
 * the map and clear of the labels placed before it. A label with no clear side is left out.
 */
export function placeLabels(requests: readonly LabelRequest[], layout: LabelLayout): PlacedLabel[] {
  const placed: PlacedLabel[] = [];
  const taken: Box[] = [];
  for (const request of requests) {
    const width = estimateLabelWidth(request.text, layout.fontSize);
    for (const side of SIDES) {
      const baseline = request.y + side.dy * layout.gap + baselineOffset(side.dy, layout.fontSize);
      const x = request.x + side.dx * layout.gap;
      const box = boxAt({ x, baseline }, width, side.anchor, layout.fontSize);
      if (isInside(box, layout.view) && !taken.some((other) => overlaps(box, other))) {
        placed.push({ id: request.id, text: request.text, x, y: baseline, anchor: side.anchor });
        taken.push(box);
        break;
      }
    }
  }
  return placed;
}

function baselineOffset(dy: number, fontSize: number): number {
  if (dy === 0) return fontSize * CENTRE_BASELINE_EM;
  return dy > 0 ? fontSize : 0;
}

function boxAt(at: { readonly x: number; readonly baseline: number }, width: number, anchor: PlacedLabel["anchor"], fontSize: number): Box {
  const left = anchor === "start" ? at.x : anchor === "end" ? at.x - width : at.x - width / 2;
  return { left, right: left + width, top: at.baseline - ASCENT_EM * fontSize, bottom: at.baseline + DESCENT_EM * fontSize };
}

function isInside(box: Box, view: LabelLayout["view"]): boolean {
  return box.left >= 0 && box.top >= 0 && box.right <= view.width && box.bottom <= view.height;
}

function overlaps(a: Box, b: Box): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}
