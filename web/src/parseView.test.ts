import { expect, it } from "vitest";
import { parseView } from "./urlState";

it.each([
  ["#accuracy", "accuracy"],
  ["#forecast", "forecast"],
  ["", "forecast"],
  ["#Accuracy", "forecast"],
  ["#unknown", "forecast"],
])("reads %j as %s", (hash, view) => {
  expect(parseView(hash)).toBe(view);
});
