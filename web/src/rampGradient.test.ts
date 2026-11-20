import { expect, it } from "vitest";
import { rampGradient } from "./chartGeometry";

it("draws the legend gradient through every ramp stop, from 0 to 300", () => {
  const gradient = rampGradient();
  expect(gradient.startsWith("linear-gradient(to right, oklch(0.950 0.045 165.0) 0.0%, ")).toBe(true);
  expect(gradient.endsWith("oklch(0.360 0.080 35.0) 100.0%)")).toBe(true);
  expect(gradient).toContain("oklch(0.660 0.110 95.0) 50.0%");
});
