import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";

beforeEach(() => {
  document.body.insertAdjacentHTML("afterbegin", '<nav id="site-nav" aria-label="Main"></nav>');
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined)));
});

afterEach(() => {
  document.getElementById("site-nav")?.remove();
  window.location.hash = "";
});

function navLinks() {
  return screen.getAllByRole("link").map((link) => [link.textContent, link.getAttribute("aria-current")]);
}

it("marks the forecast as the current page on the bare address", () => {
  render(<App apiBaseUrl="" />);
  expect(navLinks()).toEqual([
    ["Forecast", "page"],
    ["Accuracy", null],
  ]);
  expect(document.title).toBe("Gridcast: when is your electricity cleanest?");
});

it("opens the accuracy page from its address and marks it current", async () => {
  window.location.hash = "#accuracy";
  render(<App apiBaseUrl="" />);
  expect(await screen.findByRole("heading", { name: "How good is the forecast?" })).toBeTruthy();
  expect(navLinks()).toEqual([
    ["Forecast", null],
    ["Accuracy", "page"],
  ]);
  expect(document.title).toBe("How good is the forecast? Gridcast");
});

it("follows the address when it changes", async () => {
  render(<App apiBaseUrl="" />);
  act(() => {
    window.location.hash = "#accuracy";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(await screen.findByRole("heading", { name: "How good is the forecast?" })).toBeTruthy();
  act(() => {
    window.location.hash = "#forecast";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(screen.queryByRole("heading", { name: "How good is the forecast?" })).toBeNull();
  expect(navLinks()[0]).toEqual(["Forecast", "page"]);
});

it("treats an unknown hash as the forecast", () => {
  window.location.hash = "#elsewhere";
  render(<App apiBaseUrl="" />);
  expect(navLinks()[0]).toEqual(["Forecast", "page"]);
});

it("tells the visitor to reload when the accuracy page cannot be fetched", async () => {
  vi.resetModules();
  vi.doMock("./accuracy/AccuracyView", () => {
    throw new Error("the chunk could not be fetched");
  });
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  window.location.hash = "#accuracy";
  const { App: FreshApp } = await import("./App");
  render(<FreshApp apiBaseUrl="" />);
  expect((await screen.findByRole("status")).textContent).toContain("Reload the page to try again.");
  vi.doUnmock("./accuracy/AccuracyView");
});
