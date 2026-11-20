import { useCallback, useState } from "react";

interface MeasuredSize {
  readonly widthPx: number;
  readonly heightPx: number;
}

const UNMEASURED: MeasuredSize = { widthPx: 0, heightPx: 0 };

/** A ref for an element, and that element's size in pixels, kept current as it resizes. Zero until measured. */
export function useMeasuredSize() {
  const [size, setSize] = useState(UNMEASURED);
  const measure = useCallback((node: Element | null) => {
    if (node === null) return;
    const read = () => {
      const box = node.getBoundingClientRect();
      setSize((current) => (current.widthPx === box.width && current.heightPx === box.height ? current : { widthPx: box.width, heightPx: box.height }));
    };
    const observer = new ResizeObserver(read);
    observer.observe(node);
    read();
    return () => {
      observer.disconnect();
    };
  }, []);
  return [measure, size] as const;
}
