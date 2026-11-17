// Shape of mockup/snapshot.js, written by gridcast.snapshot.

type IntensityIndex = "very low" | "low" | "moderate" | "high" | "very high";

interface SnapshotWindow {
  readonly start: number;
  readonly mean: number;
}

interface WindowChoice {
  readonly cleanest: SnapshotWindow;
  readonly dirtiest: SnapshotWindow;
  readonly timingMatters: boolean;
}

interface SnapshotRegion {
  readonly id: number;
  readonly name: string;
  readonly path: string;
  readonly labelAt: readonly [number, number];
  readonly forecast: readonly number[];
  readonly index: readonly IntensityIndex[];
  readonly mix: readonly (readonly number[])[];
  readonly windows: Readonly<Record<string, WindowChoice>>;
  readonly illustrativeRange: { readonly low: readonly number[]; readonly high: readonly number[] };
}

interface PilotSummary {
  readonly n: number;
  readonly mae: number;
  readonly maeLow: number;
  readonly maeHigh: number;
  readonly p95AbsoluteError: number;
  readonly meanBias: number;
  readonly mapePercent: number;
  readonly maeByHourUtc: readonly number[];
  readonly windowHours: number;
  readonly regretThreshold: number;
  readonly daysAnalysed: number;
  readonly shareWithinThreshold: number;
  readonly shareExactBest: number;
  readonly medianRegret: number;
  readonly caveat: string;
}

interface Snapshot {
  readonly fetchedAt: string;
  readonly firstSlotStart: string;
  readonly slotMinutes: number;
  readonly slotCount: number;
  readonly fuels: readonly string[];
  readonly viewBox: readonly [number, number, number, number];
  readonly shetlandFrame: readonly [number, number, number, number];
  readonly durationsHours: readonly number[];
  readonly regions: readonly SnapshotRegion[];
  readonly pilot: PilotSummary;
}

interface Window {
  readonly GRIDCAST_SNAPSHOT: Snapshot;
}
