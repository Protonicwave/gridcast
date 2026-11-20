import { useEffect, useState } from "react";

/** Time between steps when the next 48 hours play through, so the whole series takes about nine seconds. */
const PLAY_STEP_MS = 90;

export interface CursorControl {
  /** The half hour under the cursor, never past `lastSlot`. */
  readonly cursor: number;
  readonly isPlaying: boolean;
  /** Moves the cursor and stops any playback, since the visitor has taken over. */
  readonly moveTo: (slot: number) => void;
  /** Starts stepping to the end, from the start if the cursor is already there; stops if under way. */
  readonly togglePlaying: () => void;
}

/** The half hour that the chart and the map both show, and the playback that steps it. */
export function useCursor(lastSlot: number): CursorControl {
  const [requested, setRequested] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const cursor = Math.min(requested, lastSlot);

  useEffect(() => {
    if (!isPlaying) return;
    const timer = setTimeout(() => {
      if (cursor >= lastSlot) setIsPlaying(false);
      else setRequested(cursor + 1);
    }, PLAY_STEP_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [isPlaying, cursor, lastSlot]);

  return {
    cursor,
    isPlaying,
    moveTo: (slot) => {
      setIsPlaying(false);
      setRequested(slot);
    },
    togglePlaying: () => {
      if (isPlaying) {
        setIsPlaying(false);
        return;
      }
      if (cursor >= lastSlot) setRequested(0);
      setIsPlaying(true);
    },
  };
}
