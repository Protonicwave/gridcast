import { expect, it } from "vitest";
import { estimateLabelWidth, labelledRegionIds, type LabelRequest, type PlacedLabel, placeLabels } from "./labels";

const LAYOUT = { fontSize: 10, gap: 2, view: { width: 200, height: 100 } } as const;
const WIDE_VIEW = { width: 150, height: 100 } as const;
const LONG_TEXT = "A region of 20 chars";

function request(id: number, x: number, y: number, text = "Wales 90 g"): LabelRequest {
  return { id, text, x, y };
}

/** The label's box as `placeLabels` reasons about it: 0.8 em above the baseline and 0.25 em below. */
function boxOf(label: PlacedLabel) {
  const width = estimateLabelWidth(label.text, LAYOUT.fontSize);
  const left = label.anchor === "start" ? label.x : label.anchor === "end" ? label.x - width : label.x - width / 2;
  return { left, right: left + width, top: label.y - 0.8 * LAYOUT.fontSize, bottom: label.y + 0.25 * LAYOUT.fontSize };
}

it("labels the selected region, then the cleanest and the dirtiest", () => {
  const values = new Map([[1, 120], [2, 40], [3, 300], [4, 200]]);
  expect(labelledRegionIds(values, 4)).toEqual([4, 2, 3]);
});

it("labels a region once when it is both selected and the cleanest", () => {
  const values = new Map([[1, 120], [2, 40], [3, 300]]);
  expect(labelledRegionIds(values, 2)).toEqual([2, 3]);
});

it("labels only the cleanest and the dirtiest when nothing is selected", () => {
  const values = new Map([[1, 120], [2, 40], [3, 300]]);
  expect(labelledRegionIds(values, null)).toEqual([2, 3]);
});

it("breaks a tie by region number", () => {
  const values = new Map([[5, 100], [3, 100], [4, 100]]);
  expect(labelledRegionIds(values, null)).toEqual([3, 5]);
});

it("labels nothing when there are no values", () => {
  expect(labelledRegionIds(new Map(), null)).toEqual([]);
});

it("labels nothing for a selected region that has no value", () => {
  expect(labelledRegionIds(new Map([[1, 10]]), 9)).toEqual([1]);
});

it("puts a label to the right of its anchor when there is room", () => {
  const [placed] = placeLabels([request(1, 20, 50)], LAYOUT);
  expect(placed).toMatchObject({ id: 1, anchor: "start", x: 22 });
});

it("moves a label to the left of its anchor when the right side leaves the map", () => {
  const [placed] = placeLabels([request(1, 190, 50)], LAYOUT);
  expect(placed).toMatchObject({ anchor: "end", x: 188 });
});

it("moves a label above its anchor when neither side fits", () => {
  const [placed] = placeLabels([request(1, 75, 50, LONG_TEXT)], { ...LAYOUT, view: WIDE_VIEW });
  expect(placed).toMatchObject({ anchor: "middle" });
  expect(placed?.y).toBeLessThan(50);
});

it("moves a label below its anchor when above is outside the map", () => {
  const [placed] = placeLabels([request(1, 75, 4, LONG_TEXT)], { ...LAYOUT, view: WIDE_VIEW });
  expect(placed).toMatchObject({ anchor: "middle" });
  expect(placed?.y).toBeGreaterThan(4);
});

it("moves a later label off an earlier one", () => {
  const [first, second] = placeLabels([request(1, 20, 50), request(2, 60, 52)], LAYOUT);
  expect(second).toBeDefined();
  expect([second?.x, second?.y, second?.anchor]).not.toEqual([first?.x, first?.y, first?.anchor]);
});

it("keeps every placed label inside the map and clear of the others", () => {
  const requests = [request(1, 10, 10), request(2, 100, 50), request(3, 190, 90), request(4, 105, 55), request(5, 0, 0)];
  const placed = placeLabels(requests, LAYOUT);
  expect(placed.length).toBeGreaterThan(2);
  const boxes = placed.map(boxOf);
  for (const box of boxes) {
    expect(box.left).toBeGreaterThanOrEqual(0);
    expect(box.top).toBeGreaterThanOrEqual(0);
    expect(box.right).toBeLessThanOrEqual(LAYOUT.view.width);
    expect(box.bottom).toBeLessThanOrEqual(LAYOUT.view.height);
  }
  boxes.forEach((box, index) => {
    for (const other of boxes.slice(index + 1)) {
      const apart = box.right <= other.left || other.right <= box.left || box.bottom <= other.top || other.bottom <= box.top;
      expect(apart).toBe(true);
    }
  });
});

it("leaves a label out when no side of its anchor is clear", () => {
  const crowd = [request(1, 75, 15, LONG_TEXT), request(2, 75, 15, LONG_TEXT)];
  const placed = placeLabels(crowd, { ...LAYOUT, view: { width: 150, height: 20 } });
  expect(placed.map(({ id }) => id)).toEqual([1]);
});

it("estimates a label's width from its length and font size", () => {
  expect(estimateLabelWidth("abcd", 10)).toBeCloseTo(4 * 10 * 0.56);
});
