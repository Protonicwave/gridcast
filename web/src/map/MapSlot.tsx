import { Component, lazy, type ReactNode, Suspense } from "react";
import type { RegionMapProps } from "./RegionMap";

/** Width over height of the map's view box. The box keeps this shape while the map loads, so its arrival shifts nothing. */
export const MAP_ASPECT_RATIO = 0.623;

// The map and its shapes are a separate chunk, so the answer and the chart do not wait for them.
const LazyRegionMap = lazy(() => import("./RegionMap").then((module) => ({ default: module.RegionMap })));

/** The map, loaded on demand. A map that cannot load says so and leaves the rest of the page working. */
export function MapSlot(props: RegionMapProps) {
  return (
    <MapBoundary>
      <Suspense fallback={<div className="map map--waiting" style={{ aspectRatio: MAP_ASPECT_RATIO }} aria-busy="true" />}>
        <LazyRegionMap {...props} />
      </Suspense>
    </MapBoundary>
  );
}

class MapBoundary extends Component<{ readonly children: ReactNode }, { readonly failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override componentDidCatch(error: unknown) {
    console.error("the map failed to load or draw", error);
  }

  override render() {
    if (!this.state.failed) return this.props.children;
    return (
      <p className="notice notice--warning" role="status">
        The map did not load. The list below still shows every region, and the chart works as usual.
      </p>
    );
  }
}
