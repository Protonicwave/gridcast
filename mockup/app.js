// Gridcast interface mock-up: renders the saved forecast in snapshot.js.

const SNAPSHOT = window.GRIDCAST_SNAPSHOT;
const SLOT_MS = SNAPSHOT.slotMinutes * 60_000;
const FIRST_SLOT_MS = Date.parse(SNAPSHOT.firstSlotStart);
const FETCHED_MS = Date.parse(SNAPSHOT.fetchedAt);
const SLOT_COUNT = at(SNAPSHOT.regions, 0).forecast.length;
const DAY_MS = 86_400_000;
const TIME_ZONE = "Europe/London";
const DEFAULT_HOURS = 3;
/** London, which the mock-up's state switcher and alert form fall back to when no region is chosen. */
const DEFAULT_REGION_ID = 13;
/** South West England, which covers Bristol in the assistant's example question. */
const ASK_REGION_ID = 11;
const ASK_HOURS = 4;
const WINDOW_LABEL_HALF_WIDTH_PX = 40;
const NOW_LABEL_CLEARANCE_PX = 48;
const POSTCODE_TIMEOUT_MS = 8_000;
const BUSY_DELAY_MS = 200;
const PLAY_STEP_MS = 90;
const CHART_HEIGHT_PX = 260;
const CHART_HEIGHT_NARROW_PX = 220;
const NARROW_WIDTH_PX = 520;
const MAP_LABEL_SIZE_PX = 12.5;
const LABEL_GAP_PX = 4;
const MIX_MIN_SHARE_PERCENT = 0.5;
const RAMP_MAX_G_PER_KWH = 300;
const POSTCODE_API = "https://api.carbonintensity.org.uk/regional/postcode/";
const SVG_NS = "http://www.w3.org/2000/svg";

/** Value, lightness, chroma and hue. Lightness falls steadily, so the order survives colour blindness. */
const RAMP_STOPS = /** @type {const} */ ([
  [0, 0.95, 0.045, 165],
  [50, 0.86, 0.08, 150],
  [100, 0.76, 0.1, 125],
  [150, 0.66, 0.11, 95],
  [200, 0.56, 0.11, 70],
  [250, 0.46, 0.1, 50],
  [300, 0.36, 0.08, 35],
]);

const HOURS_NOUN = new Map([[1, "hour"], [2, "two hours"], [3, "three hours"], [4, "four hours"]]);
const HOURS_ADJECTIVE = new Map([[1, "one-hour"], [2, "two-hour"], [3, "three-hour"], [4, "four-hour"]]);
const LABEL_SIDES = [
  { dx: 1, dy: 0, anchor: "start" }, { dx: -1, dy: 0, anchor: "end" },
  { dx: 0, dy: -1, anchor: "middle" }, { dx: 0, dy: 1, anchor: "middle" },
];
const VIEWS = /** @type {const} */ (["forecast", "accuracy", "alerts", "ask"]);
const MOCK_STATES = /** @type {const} */ (["live", "first", "loading", "stale", "unavailable", "range"]);
const NON_GB_PREFIXES = new Map([
  ["BT", "Northern Ireland has its own electricity grid, which Gridcast does not cover. Gridcast covers England, Scotland and Wales."],
  ["GY", "Gridcast covers England, Scotland and Wales, which share one grid. Guernsey is not part of it."],
  ["JE", "Gridcast covers England, Scotland and Wales, which share one grid. Jersey is not part of it."],
  ["IM", "Gridcast covers England, Scotland and Wales, which share one grid. The Isle of Man is not part of it."],
]);
const POSTCODE_PATTERN = /^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})?$/;

/** @typedef {typeof VIEWS[number]} View */
/** @typedef {typeof MOCK_STATES[number]} MockState */

const timeFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const hourFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, hour: "2-digit", hourCycle: "h23" });
const minuteFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, minute: "2-digit" });
const weekdayFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "long" });
const shortWeekdayFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "short" });
const dateKeyFormat = new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const longDateFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, weekday: "long", day: "numeric", month: "long" });
const fullDateFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, day: "numeric", month: "long", year: "numeric" });

const state = {
  /** @type {View} */ view: "forecast",
  /** @type {MockState} */ mockState: "live",
  /** @type {number | null} */ regionId: null,
  hours: DEFAULT_HOURS,
  cursor: 0,
  /** @type {number | null} */ playTimer: null,
  /** The postcode lookup in flight, aborted when a newer one starts. @type {AbortController | null} */
  postcodeLookup: null,
};

/** @template T @param {readonly T[]} items @param {number} index @returns {T} */
function at(items, index) {
  const item = items[index];
  if (item === undefined) throw new RangeError(`expected index 0 to ${items.length - 1}, got ${index}`);
  return item;
}

/** @param {string} id @returns {HTMLElement} */
function byId(id) {
  const node = document.getElementById(id);
  if (node === null) throw new Error(`expected element #${id} in mockup.html`);
  return node;
}

/** @param {number} id @returns {SnapshotRegion} */
function regionById(id) {
  const region = SNAPSHOT.regions.find((candidate) => candidate.id === id);
  if (region === undefined) throw new RangeError(`expected a region id from 1 to 14, got ${id}`);
  return region;
}

/** @param {SnapshotRegion} region @param {number} hours @returns {WindowChoice} */
function windowChoice(region, hours) {
  const choice = region.windows[String(hours)];
  if (choice === undefined) throw new RangeError(`expected a window length in ${SNAPSHOT.durationsHours.join(", ")}, got ${hours}`);
  return choice;
}

/** @param {number} hours */
function slotsFor(hours) {
  return (hours * 60) / SNAPSHOT.slotMinutes;
}

// Time wording

/** @param {number} slot */
function slotStartMs(slot) {
  return FIRST_SLOT_MS + slot * SLOT_MS;
}

/** @param {number} ms */
function clock(ms) {
  return timeFormat.format(ms);
}

/** @param {number} ms */
function localHour(ms) {
  return Number(hourFormat.format(ms));
}

/** @param {number} ms */
function isLocalMidnight(ms) {
  return localHour(ms) === 0 && Number(minuteFormat.format(ms)) === 0;
}

/** Whole calendar days between the snapshot's date and this instant's date, in UK time. @param {number} ms */
function daysAfterSnapshot(ms) {
  return Math.round((Date.parse(dateKeyFormat.format(ms)) - Date.parse(dateKeyFormat.format(FETCHED_MS))) / DAY_MS);
}

/** "today", "tonight", "tomorrow" or a weekday, as someone in Britain would say it on the snapshot's day. @param {number} ms */
function dayWord(ms) {
  const days = daysAfterSnapshot(ms);
  const hour = localHour(ms);
  if (days === 0) return hour >= 18 ? "tonight" : "today";
  if (days === 1) return hour < 6 ? "tonight" : "tomorrow";
  if (days === 2 && hour < 6) return "tomorrow night";
  return weekdayFormat.format(ms);
}

/** @param {string} text */
function capitalise(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The verb in agreement with "hour" or "hours": "starts" for one hour, "start" for more. @param {number} hours @param {string} verb */
function agree(hours, verb) {
  return hours === 1 ? `${verb}s` : verb;
}

/** @param {number} startSlot @param {number} slots */
function windowPhrase(startSlot, slots) {
  const start = slotStartMs(startSlot);
  const end = slotStartMs(startSlot + slots);
  if (startSlot === 0) return `now until ${clock(end)}`;
  return `${dayWord(start)}, ${clock(start)} to ${clock(end)}`;
}

/** @param {number} slot */
function slotPhrase(slot) {
  const start = slotStartMs(slot);
  return slot === 0 ? "now" : `${dayWord(start)} ${clock(start)}`;
}

/** @param {number} value */
function grams(value) {
  return `${Math.round(value)} g`;
}

// Colour

/** @param {number} value */
function rampColour(value) {
  const clamped = Math.min(Math.max(value, 0), RAMP_MAX_G_PER_KWH);
  for (let i = 1; i < RAMP_STOPS.length; i += 1) {
    const upper = at(RAMP_STOPS, i);
    if (clamped <= upper[0]) {
      const lower = at(RAMP_STOPS, i - 1);
      const t = (clamped - lower[0]) / (upper[0] - lower[0]);
      const mix = (/** @type {number} */ a, /** @type {number} */ b) => a + (b - a) * t;
      return `oklch(${mix(lower[1], upper[1]).toFixed(3)} ${mix(lower[2], upper[2]).toFixed(3)} ${mix(lower[3], upper[3]).toFixed(1)})`;
    }
  }
  throw new RangeError(`expected a finite intensity, got ${value}`);
}

function rampGradient() {
  const stops = RAMP_STOPS.map(([value]) => `${rampColour(value)} ${((value / RAMP_MAX_G_PER_KWH) * 100).toFixed(1)}%`);
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

// URL state

function readUrl() {
  const params = new URLSearchParams(location.search);
  const hash = location.hash.slice(1);
  state.view = VIEWS.find((view) => view === hash) ?? "forecast";
  const mock = params.get("state");
  state.mockState = MOCK_STATES.find((candidate) => candidate === mock) ?? "live";
  const region = Number(params.get("region"));
  state.regionId = SNAPSHOT.regions.some((candidate) => candidate.id === region) ? region : null;
  const hours = Number(params.get("hours"));
  state.hours = SNAPSHOT.durationsHours.includes(hours) ? hours : DEFAULT_HOURS;
}

function writeUrl() {
  const params = new URLSearchParams();
  if (state.regionId !== null) params.set("region", String(state.regionId));
  if (state.hours !== DEFAULT_HOURS) params.set("hours", String(state.hours));
  if (state.mockState !== "live") params.set("state", state.mockState);
  const url = new URL(location.href);
  url.search = params.toString();
  url.hash = state.view;
  history.replaceState(null, "", url);
}

/** The region the forecast view shows, after the mock-up state is applied. */
function shownRegion() {
  if (state.mockState === "first" || state.regionId === null) return null;
  return regionById(state.regionId);
}

// Answer

function renderAnswer() {
  const answer = byId("answer");
  const region = shownRegion();
  const detail = byId("forecast-detail");
  if (state.mockState === "loading") {
    answer.innerHTML = `<p class="answer__label">${region ? region.name : "Great Britain"}</p><h1 id="answer-heading">Loading the forecast…</h1>`;
    detail.hidden = true;
    return;
  }
  if (region === null) {
    answer.innerHTML = `<h1 id="answer-heading">When is your electricity cleanest?</h1>
      <p class="answer__detail">Enter a postcode, or pick a region on the map, to see the cleanest time to use electricity there in the next 48 hours.</p>`;
    detail.hidden = true;
    return;
  }
  detail.hidden = false;
  const choice = windowChoice(region, state.hours);
  const slots = slotsFor(state.hours);
  const noun = HOURS_NOUN.get(state.hours) ?? "";
  if (choice.timingMatters) {
    answer.innerHTML = `<p class="answer__label">Cleanest ${noun} in ${region.name}</p>
      <h1 id="answer-heading">${capitalise(windowPhrase(choice.cleanest.start, slots))}</h1>
      <p class="answer__detail">About <strong class="nowrap">${grams(choice.cleanest.mean)}</strong> of CO<sub>2</sub> per kWh. The dirtiest ${noun}, ${windowPhrase(choice.dirtiest.start, slots)}, ${agree(state.hours, "average")} <span class="nowrap">${grams(choice.dirtiest.mean)}</span>.</p>`;
  } else {
    answer.innerHTML = `<p class="answer__label">Next 48 hours in ${region.name}</p>
      <h1 id="answer-heading">Any time works about as well</h1>
      <p class="answer__detail">Every ${HOURS_ADJECTIVE.get(state.hours) ?? ""} window averages ${spreadPhrase(choice)} of CO<sub>2</sub> per kWh, so there is little to gain by waiting.</p>`;
  }
}

/** @param {WindowChoice} choice */
function spreadPhrase(choice) {
  const low = Math.round(choice.cleanest.mean);
  const high = Math.round(choice.dirtiest.mean);
  if (low === high) return `about <span class="nowrap">${grams(low)}</span>`;
  return `between <span class="nowrap">${grams(low)}</span> and <span class="nowrap">${grams(high)}</span>`;
}

function renderLengthOptions() {
  const options = SNAPSHOT.durationsHours.map((hours) => `<input type="radio" name="hours" id="hours-${hours}" value="${hours}"${hours === state.hours ? " checked" : ""}><label for="hours-${hours}">${hours} h</label>`);
  byId("length-options").innerHTML = options.join("");
}

// Chart

/** @param {number} max */
function niceCeiling(max) {
  return Math.max(100, Math.ceil(max / 50) * 50);
}

/** Step line through half-hourly values, one flat segment per slot. @param {readonly number[]} values @param {(i: number) => number} x @param {(v: number) => number} y */
function stepPath(values, x, y) {
  const parts = [`M${x(0).toFixed(1)} ${y(at(values, 0)).toFixed(1)}`];
  values.forEach((value, i) => {
    if (i > 0) parts.push(`V${y(value).toFixed(1)}`);
    parts.push(`H${x(i + 1).toFixed(1)}`);
  });
  return parts.join("");
}

/** @param {readonly number[]} high @param {readonly number[]} low @param {(i: number) => number} x @param {(v: number) => number} y */
function rangePath(high, low, x, y) {
  const back = [`V${y(at(low, low.length - 1)).toFixed(1)}`];
  for (let i = low.length - 1; i >= 0; i -= 1) {
    back.push(`H${x(i).toFixed(1)}`);
    if (i > 0) back.push(`V${y(at(low, i - 1)).toFixed(1)}`);
  }
  return `${stepPath(high, x, y)}${back.join("")}Z`;
}

/** The chart's size and scales for one region, shared by drawing, the cursor and pointer input. @param {SnapshotRegion} region */
function chartScales(region) {
  const width = Math.max(byId("chart").clientWidth, 280);
  const height = width < NARROW_WIDTH_PX ? CHART_HEIGHT_NARROW_PX : CHART_HEIGHT_PX;
  const margin = { left: 36, right: 6, top: 30, bottom: 44 };
  const plotWidth = width - margin.left - margin.right;
  const plotBottom = height - margin.bottom;
  const showRange = state.mockState === "range";
  const top = niceCeiling(Math.max(...region.forecast, ...(showRange ? region.illustrativeRange.high : [0])));
  const x = (/** @type {number} */ slot) => margin.left + (slot / SLOT_COUNT) * plotWidth;
  const y = (/** @type {number} */ value) => margin.top + (1 - value / top) * (plotBottom - margin.top);
  return { width, height, margin, plotWidth, plotBottom, showRange, top, x, y };
}

function renderChart() {
  const region = shownRegion();
  if (region === null || state.mockState === "loading") return;
  const { width, height, margin, plotWidth, plotBottom, showRange, top, x, y } = chartScales(region);
  const count = SLOT_COUNT;
  const choice = windowChoice(region, state.hours);
  const slots = slotsFor(state.hours);
  const parts = [];

  const tickStep = top > 200 ? 100 : 50;
  for (let v = 0; v <= top; v += tickStep) {
    parts.push(`<line class="gridline" x1="${margin.left}" x2="${width - margin.right}" y1="${y(v)}" y2="${y(v)}"/>`);
    parts.push(`<text x="${margin.left - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`);
  }

  for (let i = 0; i <= count; i += 1) {
    const ms = slotStartMs(i);
    const hour = localHour(ms);
    if (Number(minuteFormat.format(ms)) !== 0 || hour % 6 !== 0) continue;
    if (isLocalMidnight(ms) && i > 0) {
      parts.push(`<line class="dayline" x1="${x(i)}" x2="${x(i)}" y1="${margin.top}" y2="${plotBottom + 14}"/>`);
    }
    const label = hour === 0 ? shortWeekdayFormat.format(ms) : String(hour).padStart(2, "0");
    if (i > 0 && i < count) parts.push(`<text x="${x(i)}" y="${plotBottom + 30}" text-anchor="middle" class="${hour === 0 ? "tick-day" : ""}">${label}</text>`);
  }

  const windowLeft = x(choice.cleanest.start);
  const windowRight = x(choice.cleanest.start + slots);
  if (choice.timingMatters) {
    parts.push(`<rect class="window-band" x="${windowLeft}" y="${margin.top}" width="${windowRight - windowLeft}" height="${plotBottom - margin.top}"/>`);
    parts.push(`<line class="window-edge" x1="${windowLeft}" x2="${windowRight}" y1="${margin.top}" y2="${margin.top}"/>`);
    const labelX = Math.min(Math.max((windowLeft + windowRight) / 2, margin.left + WINDOW_LABEL_HALF_WIDTH_PX), width - margin.right - WINDOW_LABEL_HALF_WIDTH_PX);
    parts.push(`<text class="window-label halo" x="${labelX}" y="${margin.top - 8}" text-anchor="middle">Cleanest ${state.hours} h</text>`);
  }
  if (showRange) parts.push(`<path class="range" d="${rangePath(region.illustrativeRange.high, region.illustrativeRange.low, x, y)}"/>`);
  parts.push(`<path class="series" d="${stepPath(region.forecast, x, y)}"/>`);

  const cellWidth = plotWidth / count;
  region.forecast.forEach((value, i) => {
    parts.push(`<rect x="${(x(i) - 0.2).toFixed(1)}" y="${plotBottom + 4}" width="${(cellWidth + 0.4).toFixed(1)}" height="8" fill="${rampColour(value)}" shape-rendering="crispEdges"/>`);
  });

  const nowX = x((FETCHED_MS - FIRST_SLOT_MS) / SLOT_MS);
  parts.push(`<line class="now-line" x1="${nowX}" x2="${nowX}" y1="${margin.top}" y2="${plotBottom}"/>`);
  if (!choice.timingMatters || windowLeft - nowX > NOW_LABEL_CLEARANCE_PX) {
    parts.push(`<text class="now-label halo" x="${nowX}" y="${margin.top - 8}" text-anchor="start">Now</text>`);
  }
  parts.push(`<line class="cursor-line" id="cursor-line" y1="${margin.top}" y2="${plotBottom}"/>`);
  parts.push(`<circle class="cursor-dot" id="cursor-dot" r="4.5"/>`);

  byId("chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true">${parts.join("")}</svg>`;
  placeCursor();
}

function placeCursor() {
  const region = shownRegion();
  const line = document.getElementById("cursor-line");
  const dot = document.getElementById("cursor-dot");
  if (region === null || line === null || dot === null) return;
  const { x, y } = chartScales(region);
  const centre = x(state.cursor + 0.5);
  const value = at(region.forecast, state.cursor);
  line.setAttribute("x1", centre.toFixed(1));
  line.setAttribute("x2", centre.toFixed(1));
  dot.setAttribute("cx", centre.toFixed(1));
  dot.setAttribute("cy", y(value).toFixed(1));
  const chart = byId("chart");
  chart.setAttribute("aria-valuemax", String(SLOT_COUNT - 1));
  chart.setAttribute("aria-valuenow", String(state.cursor));
  chart.setAttribute("aria-valuetext", `${slotPhrase(state.cursor)}, ${Math.round(value)} grams per kilowatt hour, ${at(region.index, state.cursor)}`);
}

function renderChartFrame() {
  const region = shownRegion();
  if (region === null) return;
  byId("chart-heading").textContent = `Next 48 hours in ${region.name}`;
  const showRange = state.mockState === "range";
  const key = [
    `<li><span class="key__swatch key__swatch--line"></span><span>${showRange ? "Forecast" : "NESO forecast"}, g CO<sub>2</sub> per kWh</span></li>`,
    `<li><span class="key__swatch key__swatch--window"></span>Cleanest ${HOURS_NOUN.get(state.hours) ?? ""}</li>`,
  ];
  if (showRange) key.push(`<li><span class="key__swatch key__swatch--range"></span>Likely range</li>`);
  byId("chart-key").innerHTML = key.join("");
  byId("range-note").hidden = !showRange;
}

/** @param {number} clientX */
function cursorFromPointer(clientX) {
  const svg = byId("chart").querySelector("svg");
  const region = shownRegion();
  if (svg === null || region === null) return;
  const box = svg.getBoundingClientRect();
  const { width, margin, plotWidth } = chartScales(region);
  const px = ((clientX - box.left) / box.width) * width;
  const slot = Math.floor(((px - margin.left) / plotWidth) * SLOT_COUNT);
  setCursor(Math.min(Math.max(slot, 0), SLOT_COUNT - 1));
}

/** @param {number} slot */
function setCursor(slot) {
  state.cursor = slot;
  placeCursor();
  renderMapColours();
  renderReadout();
}

// Readout

function renderReadout() {
  const region = shownRegion();
  const readout = byId("readout");
  if (region === null) return;
  const value = at(region.forecast, state.cursor);
  const mix = at(region.mix, state.cursor);
  const rows = SNAPSHOT.fuels
    .map((fuel, i) => ({ name: capitalise(fuel), share: at(mix, i) }))
    .filter((row) => row.share >= MIX_MIN_SHARE_PERCENT)
    .sort((a, b) => b.share - a.share)
    .map((row) => `<dt>${row.name}</dt><dd class="mix__bar" aria-hidden="true"><span style="transform: scaleX(${(row.share / 100).toFixed(3)})"></span></dd><dd>${row.share.toFixed(0)}%</dd>`);
  const start = slotStartMs(state.cursor);
  readout.innerHTML = `<h2>${capitalise(dayWord(start))}, ${clock(start)} to ${clock(start + SLOT_MS)}</h2>
    <p class="readout__value">${Math.round(value)} g CO<sub>2</sub> per kWh <span class="readout__band">NESO rates this ${at(region.index, state.cursor)}</span></p>
    <h3 class="small" style="margin-bottom: var(--space-2)">Where the electricity comes from</h3>
    <dl class="mix">${rows.join("")}</dl>`;
}

// Map

function renderMapShapes() {
  const [vx, vy, vw, vh] = SNAPSHOT.viewBox;
  const [fx, fy, fw, fh] = SNAPSHOT.shetlandFrame;
  const paths = SNAPSHOT.regions.map((region) => `<path class="region" data-region="${region.id}" d="${region.path}"><title>${region.name}</title></path>`);
  byId("map").innerHTML = `<svg viewBox="${vx} ${vy} ${vw} ${vh}" role="img" aria-labelledby="map-heading">
    <rect class="inset-frame" x="${fx}" y="${fy}" width="${fw}" height="${fh}"/>
    <g id="map-regions">${paths.join("")}</g><g id="map-labels"></g></svg>`;
  byId("legend-ramp").style.background = rampGradient();
}

function renderMapColours() {
  const empty = state.mockState === "loading";
  const selected = shownRegion();
  for (const path of byId("map").querySelectorAll("path.region")) {
    const region = regionById(Number(path.getAttribute("data-region")));
    path.classList.toggle("region--empty", empty);
    path.classList.toggle("region--selected", selected !== null && region.id === selected.id);
    path.setAttribute("fill", empty ? "" : rampColour(at(region.forecast, state.cursor)));
  }
  byId("map-heading").textContent = empty ? "Across Great Britain" : `Across Great Britain, ${slotPhrase(state.cursor)}`;
  renderMapLabels();
}

/** The selected region and the cleanest and dirtiest at the cursor, in priority order. */
function labelledRegions() {
  if (state.mockState === "loading") return [];
  const byValue = [...SNAPSHOT.regions].sort((a, b) => at(a.forecast, state.cursor) - at(b.forecast, state.cursor));
  const chosen = [shownRegion(), byValue[0], byValue[byValue.length - 1]];
  /** @type {SnapshotRegion[]} */
  const unique = [];
  for (const region of chosen) {
    if (region && !unique.some((other) => other.id === region.id)) unique.push(region);
  }
  return unique;
}

/** @param {DOMRect | SVGRect} a @param {DOMRect | SVGRect} b */
function overlaps(a, b) {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

/**
 * Moves the label to the first side of its anchor where it stays inside the map and clear of earlier labels.
 * @param {SVGTextElement} text @param {readonly [number, number]} anchor @param {number} gap @param {number} size
 * @param {DOMRect} view @param {readonly (DOMRect | SVGRect)[]} taken
 * @returns {DOMRect | null} the label's box, or null when no side is clear
 */
function placeLabel(text, anchor, gap, size, view, taken) {
  const [ax, ay] = anchor;
  for (const side of LABEL_SIDES) {
    const baselineOffset = side.dy === 0 ? size * 0.35 : side.dy > 0 ? size : 0;
    text.setAttribute("x", (ax + side.dx * gap).toFixed(2));
    text.setAttribute("y", (ay + side.dy * gap + baselineOffset).toFixed(2));
    text.setAttribute("text-anchor", side.anchor);
    const labelBox = text.getBBox();
    const inside = labelBox.x >= view.x && labelBox.y >= view.y
      && labelBox.x + labelBox.width <= view.x + view.width && labelBox.y + labelBox.height <= view.y + view.height;
    if (inside && !taken.some((other) => overlaps(labelBox, other))) return labelBox;
  }
  return null;
}

function renderMapLabels() {
  const svg = byId("map").querySelector("svg");
  const layer = document.getElementById("map-labels");
  if (svg === null || layer === null) return;
  layer.replaceChildren();
  // The map keeps its aspect ratio inside a height-limited box, so the drawn scale is the larger ratio.
  const svgBox = svg.getBoundingClientRect();
  const scale = Math.max(SNAPSHOT.viewBox[2] / Math.max(svgBox.width, 1), SNAPSHOT.viewBox[3] / Math.max(svgBox.height, 1));
  const size = MAP_LABEL_SIZE_PX * scale;
  const gap = LABEL_GAP_PX * scale;
  const view = svg.viewBox.baseVal;
  /** @type {(DOMRect | SVGRect)[]} */
  const taken = [];
  for (const region of labelledRegions()) {
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("font-size", size.toFixed(2));
    text.setAttribute("stroke-width", (3 * scale).toFixed(2));
    const name = document.createElementNS(SVG_NS, "tspan");
    name.setAttribute("class", "label-name");
    name.textContent = region.name;
    const value = document.createElementNS(SVG_NS, "tspan");
    value.setAttribute("class", "label-value");
    value.textContent = ` ${Math.round(at(region.forecast, state.cursor))} g`;
    text.append(name, value);
    layer.append(text);
    const placed = placeLabel(text, region.labelAt, gap, size, view, taken);
    if (placed === null) text.remove();
    else taken.push(placed);
  }
}

// Region list

function renderList() {
  const list = byId("region-list");
  const noun = HOURS_NOUN.get(state.hours) ?? "";
  byId("list-heading").textContent = state.mockState === "loading" ? "Every region" : `Every region's cleanest ${noun}`;
  if (state.mockState === "loading") {
    list.innerHTML = "";
    return;
  }
  const slots = slotsFor(state.hours);
  const selected = shownRegion();
  const ordered = [...SNAPSHOT.regions].sort((a, b) => windowChoice(a, state.hours).cleanest.mean - windowChoice(b, state.hours).cleanest.mean || a.name.localeCompare(b.name));
  list.innerHTML = ordered.map((region) => {
    const choice = windowChoice(region, state.hours);
    const cells = region.forecast.map((value, i) => `<rect x="${i}" width="1.05" height="1" fill="${rampColour(value)}"/>`).join("");
    const bracket = choice.timingMatters ? `<rect x="${choice.cleanest.start}" width="${slots}" height="1" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/>` : "";
    const when = choice.timingMatters
      ? `${capitalise(slotPhrase(choice.cleanest.start))}, ${grams(choice.cleanest.mean)}`
      : `Any time, ${spreadPhrase(choice)}`;
    return `<li><button class="region-row" type="button" data-region="${region.id}" aria-pressed="${selected !== null && selected.id === region.id}">
      <span class="region-row__name">${region.name}</span><span class="region-row__when">${when}</span>
      <svg class="region-row__strip" viewBox="0 0 ${SLOT_COUNT} 1" preserveAspectRatio="none" aria-hidden="true">${cells}${bracket}</svg>
    </button></li>`;
  }).join("");
}

// Postcode lookup

/** @param {string} message */
function showPostcodeMessage(message) {
  const node = byId("postcode-message");
  node.textContent = message;
  node.hidden = message === "";
  byId("postcode").setAttribute("aria-invalid", String(message !== ""));
}

/** @param {unknown} payload @returns {number} */
function regionIdFromLookup(payload) {
  if (typeof payload === "object" && payload !== null && "data" in payload && Array.isArray(payload.data)) {
    const first = payload.data[0];
    if (typeof first === "object" && first !== null && "regionid" in first && typeof first.regionid === "number" && SNAPSHOT.regions.some((r) => r.id === first.regionid)) {
      return first.regionid;
    }
  }
  throw new TypeError("expected data[0].regionid between 1 and 14 in NESO's postcode response");
}

/** @param {SubmitEvent} event */
async function lookUpPostcode(event) {
  event.preventDefault();
  const input = /** @type {HTMLInputElement} */ (byId("postcode"));
  const button = /** @type {HTMLButtonElement} */ (byId("postcode-submit"));
  const cleaned = input.value.toUpperCase().replace(/\s+/g, "");
  if (cleaned === "") return showPostcodeMessage("Enter a postcode, such as BS1 or BS1 4DJ.");
  const match = POSTCODE_PATTERN.exec(cleaned);
  if (match === null) return showPostcodeMessage("That doesn't look like a UK postcode. Try the first half, such as BS1.");
  const outward = match[1] ?? cleaned;
  const nonGb = NON_GB_PREFIXES.get(outward.slice(0, 2));
  if (nonGb !== undefined) return showPostcodeMessage(nonGb);

  state.postcodeLookup?.abort();
  const lookup = new AbortController();
  state.postcodeLookup = lookup;
  showPostcodeMessage("");
  const busy = setTimeout(() => {
    button.setAttribute("aria-busy", "true");
    button.textContent = "Finding…";
  }, BUSY_DELAY_MS);
  /** @type {number | null} */
  let regionId = null;
  try {
    const signal = AbortSignal.any([lookup.signal, AbortSignal.timeout(POSTCODE_TIMEOUT_MS)]);
    const response = await fetch(`${POSTCODE_API}${encodeURIComponent(outward)}`, { signal });
    if (!response.ok) throw new Error(`postcode lookup returned HTTP ${response.status}`);
    regionId = regionIdFromLookup(await response.json());
  } catch (error) {
    if (!(error instanceof Error)) throw error;
    // NESO's error responses carry no CORS header, so the browser cannot tell an unknown postcode from a network failure.
    if (!lookup.signal.aborted) showPostcodeMessage(`NESO's lookup didn't find ${outward}, or couldn't be reached. Check the postcode, or pick your region on the map.`);
  } finally {
    clearTimeout(busy);
    if (state.postcodeLookup === lookup) {
      state.postcodeLookup = null;
      button.removeAttribute("aria-busy");
      button.textContent = "Find region";
    }
  }
  if (regionId !== null && !lookup.signal.aborted) selectRegion(regionId);
}

// Accuracy

function renderAccuracy() {
  const pilot = SNAPSHOT.pilot;
  const within = Math.round(pilot.shareWithinThreshold * 100);
  const exact = Math.round(pilot.shareExactBest * 100);
  byId("pilot-figures").innerHTML = `
    <div><dt>${pilot.mae.toFixed(1)} g</dt><dd>Average error per kWh over ${pilot.n.toLocaleString("en-GB")} half hours. The 95% interval is ${pilot.maeLow.toFixed(1)} to ${pilot.maeHigh.toFixed(1)} g.</dd></div>
    <div><dt>Under ${Math.round(pilot.p95AbsoluteError)} g</dt><dd>The error in 95 of every 100 half hours.</dd></div>
    <div><dt>${within} in 100 days</dt><dd>The forecast's cleanest ${HOURS_NOUN.get(pilot.windowHours) ?? `${pilot.windowHours} hours`} came within ${Math.round(pilot.regretThreshold * 100)}% of the day's actual best. It picked exactly the best ones on ${exact} days in 100.</dd></div>`;
  renderHourChart();
}

function renderHourChart() {
  const values = SNAPSHOT.pilot.maeByHourUtc;
  const width = 760;
  const height = 220;
  const margin = { left: 30, right: 8, top: 12, bottom: 28 };
  const top = Math.max(5, Math.ceil(Math.max(...values) / 5) * 5);
  const band = (width - margin.left - margin.right) / values.length;
  const y = (/** @type {number} */ v) => margin.top + (1 - v / top) * (height - margin.top - margin.bottom);
  const parts = [];
  for (let v = 0; v <= top; v += 5) {
    parts.push(`<line x1="${margin.left}" x2="${width - margin.right}" y1="${y(v)}" y2="${y(v)}" stroke="var(--n-6)"/><text x="${margin.left - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`);
  }
  values.forEach((value, hour) => {
    const x = margin.left + hour * band;
    parts.push(`<rect class="bar" x="${(x + 2).toFixed(1)}" y="${y(value).toFixed(1)}" width="${(band - 4).toFixed(1)}" height="${(y(0) - y(value)).toFixed(1)}"><title>${String(hour).padStart(2, "0")}:00 UTC: ${value.toFixed(1)} g</title></rect>`);
    if (hour % 3 === 0) parts.push(`<text x="${(x + band / 2).toFixed(1)}" y="${height - 8}" text-anchor="middle">${String(hour).padStart(2, "0")}</text>`);
  });
  parts.push(`<line class="mean-line" x1="${margin.left}" x2="${width - margin.right}" y1="${y(SNAPSHOT.pilot.mae)}" y2="${y(SNAPSHOT.pilot.mae)}"/>`);
  byId("hour-chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="hour-heading">${parts.join("")}</svg>`;
}

// Alerts

function renderAlertOptions() {
  const select = /** @type {HTMLSelectElement} */ (byId("alert-region"));
  select.innerHTML = SNAPSHOT.regions.map((region) => `<option value="${region.id}">${region.name}</option>`).join("");
  select.value = String(state.regionId ?? DEFAULT_REGION_ID);
  byId("alert-length").innerHTML = SNAPSHOT.durationsHours.map((hours) => `<input type="radio" name="alert-hours" id="alert-hours-${hours}" value="${hours}"${hours === state.hours ? " checked" : ""}><label for="alert-hours-${hours}">${hours} h</label>`).join("");
}

function alertSettings() {
  const form = /** @type {HTMLFormElement} */ (byId("alerts-form"));
  const fields = new FormData(form);
  return {
    region: regionById(Number(fields.get("region"))),
    hours: Number(fields.get("alert-hours")),
    when: String(fields.get("when")),
    skip: fields.get("skip") !== null,
  };
}

/** The notification text for these alert settings, or why none would be sent. */
function alertText() {
  const { region, hours, when, skip } = alertSettings();
  const choice = windowChoice(region, hours);
  if (skip && !choice.timingMatters) return `No alert for now: timing makes little difference in ${region.name} over the next two days.`;
  const subject = `Your cleanest ${HOURS_NOUN.get(hours) ?? ""} in ${region.name}`;
  const start = slotStartMs(choice.cleanest.start);
  const end = slotStartMs(choice.cleanest.start + slotsFor(hours));
  if (when === "start" || choice.cleanest.start === 0) return `${subject} ${agree(hours, "start")} now and ${agree(hours, "run")} until ${clock(end)}.`;
  if (when === "hour") return `${subject} ${agree(hours, "start")} in one hour, at ${clock(start)}.`;
  return `${subject} ${agree(hours, "start")} at ${clock(start)} ${dayWord(start)}, at about ${Math.round(choice.cleanest.mean)} g of CO₂ per kWh.`;
}

function renderAlertPreview() {
  byId("alert-preview").textContent = alertText();
}

/** @param {SubmitEvent} event */
function turnOnAlerts(event) {
  event.preventDefault();
  const { region, hours, when } = alertSettings();
  const timing = new Map([["evening", "told at 18:00 the evening before"], ["hour", "told one hour before"], ["start", "told when it starts"]]);
  byId("alerts-confirmation-text").textContent = `Alerts on for ${region.name}: your cleanest ${HOURS_NOUN.get(hours) ?? ""}, ${timing.get(when) ?? ""}.`;
  byId("alerts-form").hidden = true;
  byId("alerts-confirmation").hidden = false;
  byId("alerts-off").focus();
}

function turnOffAlerts() {
  byId("alerts-confirmation").hidden = true;
  byId("alerts-form").hidden = false;
  byId("alerts-submit").focus();
}

// Ask

function renderAsk() {
  const region = regionById(ASK_REGION_ID);
  const noun = HOURS_NOUN.get(ASK_HOURS) ?? "";
  const choice = windowChoice(region, ASK_HOURS);
  const now = at(region.forecast, 0);
  const cut = Math.round((1 - choice.cleanest.mean / Math.max(now, 1)) * 100);
  const start = slotStartMs(choice.cleanest.start);
  const end = slotStartMs(choice.cleanest.start + slotsFor(ASK_HOURS));
  const when = choice.cleanest.start === 0 ? `start now and run until ${clock(end)}` : `start ${dayWord(start)} at ${clock(start)} and run until ${clock(end)}`;
  byId("ask-lookup").innerHTML = `Looked up <code>cleanest_window</code> for ${region.name}, which covers Bristol: ${noun}, forecast fetched ${clock(FETCHED_MS)} ${dayWord(FETCHED_MS)}.`;
  const comparison = cut > 0
    ? `Right now the grid there is at ${Math.round(now)} g, so electricity in that window is about ${cut}% less carbon-intensive.`
    : `That is about the same as right now, ${Math.round(now)} g, so there is no need to wait.`;
  byId("ask-answer").textContent = `The cleanest ${noun} for charging in ${region.name} ${when}, at about ${Math.round(choice.cleanest.mean)} g of CO₂ per kWh. ${comparison}`;
}

// Playback

function stopPlaying() {
  if (state.playTimer !== null) clearInterval(state.playTimer);
  state.playTimer = null;
  byId("play").textContent = "Play the next 48 hours";
}

function togglePlaying() {
  if (state.playTimer !== null) return stopPlaying();
  if (state.cursor >= SLOT_COUNT - 1) setCursor(0);
  byId("play").textContent = "Pause";
  state.playTimer = window.setInterval(() => {
    if (state.cursor >= SLOT_COUNT - 1) return stopPlaying();
    setCursor(state.cursor + 1);
  }, PLAY_STEP_MS);
}

// Views and wiring

function renderView() {
  const unavailable = state.mockState === "unavailable" && state.view === "forecast";
  for (const section of document.querySelectorAll("[data-view]")) {
    if (section instanceof HTMLElement) section.hidden = section.dataset["view"] !== state.view || unavailable;
  }
  byId("view-unavailable").hidden = !unavailable;
  for (const link of document.querySelectorAll("[data-view-link]")) {
    if (!(link instanceof HTMLElement)) continue;
    if (link.dataset["viewLink"] === state.view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  byId("notice-stale").hidden = state.mockState !== "stale";
  byId("freshness").textContent = state.mockState === "loading" ? "" : `Forecast fetched ${clock(FETCHED_MS)} ${dayWord(FETCHED_MS)}, ${longDateFormat.format(FETCHED_MS)}. NESO updates it every half hour.`;
}

function renderForecast() {
  renderAnswer();
  renderLengthOptions();
  renderChartFrame();
  renderChart();
  renderReadout();
  renderMapColours();
  renderList();
}

function renderAll() {
  renderView();
  if (state.view === "forecast") renderForecast();
  if (state.view === "alerts") renderAlertPreview();
}

/** @param {number} id */
function selectRegion(id) {
  if (state.mockState === "first") {
    state.mockState = "live";
    /** @type {HTMLSelectElement} */ (byId("mockup-state")).value = "live";
  }
  state.regionId = id;
  writeUrl();
  renderForecast();
}

function wire() {
  // lookUpPostcode reports its own failures to the user; anything it rethrows is a bug, left to surface as an unhandled rejection.
  byId("postcode-form").addEventListener("submit", (event) => void lookUpPostcode(/** @type {SubmitEvent} */ (event)));
  byId("length-options").addEventListener("change", (event) => {
    if (!(event.target instanceof HTMLInputElement)) return;
    state.hours = Number(event.target.value);
    writeUrl();
    renderForecast();
  });
  const regionClick = (/** @type {Event} */ event) => {
    if (!(event.target instanceof Element)) return;
    const holder = event.target.closest("[data-region]");
    if (holder !== null && state.mockState !== "loading") selectRegion(Number(holder.getAttribute("data-region")));
  };
  byId("map").addEventListener("click", regionClick);
  byId("region-list").addEventListener("click", regionClick);

  const chart = byId("chart");
  chart.addEventListener("pointerdown", (event) => {
    stopPlaying();
    chart.setPointerCapture(event.pointerId);
    cursorFromPointer(event.clientX);
  });
  chart.addEventListener("pointermove", (event) => {
    if (event.pointerType === "mouse" || chart.hasPointerCapture(event.pointerId)) cursorFromPointer(event.clientX);
  });
  chart.addEventListener("keydown", (event) => {
    const steps = new Map([["ArrowLeft", -1], ["ArrowRight", 1], ["PageUp", -12], ["PageDown", 12]]);
    const step = steps.get(event.key);
    let next = step === undefined ? null : state.cursor + step;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = SLOT_COUNT - 1;
    if (next === null) return;
    event.preventDefault();
    stopPlaying();
    setCursor(Math.min(Math.max(next, 0), SLOT_COUNT - 1));
  });
  byId("play").addEventListener("click", togglePlaying);

  const mockSelect = /** @type {HTMLSelectElement} */ (byId("mockup-state"));
  mockSelect.addEventListener("change", () => {
    state.mockState = MOCK_STATES.find((candidate) => candidate === mockSelect.value) ?? "live";
    if (state.mockState !== "first" && state.regionId === null) state.regionId = DEFAULT_REGION_ID;
    stopPlaying();
    writeUrl();
    renderAll();
  });
  byId("retry").addEventListener("click", () => {
    state.mockState = "live";
    mockSelect.value = "live";
    writeUrl();
    renderAll();
  });

  byId("alerts-form").addEventListener("change", renderAlertPreview);
  byId("alerts-form").addEventListener("submit", (event) => turnOnAlerts(/** @type {SubmitEvent} */ (event)));
  byId("alerts-off").addEventListener("click", turnOffAlerts);

  window.addEventListener("hashchange", () => {
    stopPlaying();
    readUrl();
    mockSelect.value = state.mockState;
    renderAll();
  });
  new ResizeObserver(() => {
    if (state.view !== "forecast") return;
    renderChart();
    renderMapLabels();
  }).observe(byId("main"));
}

/** Called from the end of mockup.html's body, once every element exists. */
function start() {
  readUrl();
  /** @type {HTMLSelectElement} */ (byId("mockup-state")).value = state.mockState;
  byId("mockup-fetched").textContent = `${fullDateFormat.format(FETCHED_MS)} at ${clock(FETCHED_MS)}`;
  renderMapShapes();
  renderAccuracy();
  renderAlertOptions();
  renderAsk();
  wire();
  renderAll();
}

