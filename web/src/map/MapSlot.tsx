import { lazy, Suspense } from "react";
import { ChunkBoundary } from "../ChunkBoundary";
import type { RegionMapProps } from "./RegionMap";

/** Width over height of the map's view box. The box keeps this shape while the map loads, so its arrival shifts nothing. */
export const MAP_ASPECT_RATIO = 0.623;

// The map and its shapes are a separate chunk, so the answer and the chart do not wait for them.
const LazyRegionMap = lazy(() => import("./RegionMap").then((module) => ({ default: module.RegionMap })));

/** The map, loaded on demand. A map that cannot load says so and leaves the rest of the page working. */
export function MapSlot(props: RegionMapProps) {
  return (
    <ChunkBoundary what="the map" message="The map did not load. The list below still shows every region, and the chart works as usual.">
      <Suspense fallback={<div className="map map--waiting" style={{ aspectRatio: MAP_ASPECT_RATIO }} aria-busy="true" />}>
        <LazyRegionMap {...props} />
      </Suspense>
    </ChunkBoundary>
  );
}
