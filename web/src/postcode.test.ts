import { expect, it, vi } from "vitest";
import { lookUpRegion, outwardCode, PostcodeError, PostcodeLookupError } from "./postcode";

it.each([
  ["BS1", "BS1"],
  ["bs1 4dj", "BS1"],
  ["BS14DJ", "BS1"],
  ["  sw1a 1aa ", "SW1A"],
  ["M60 1NW", "M60"],
  ["E1", "E1"],
])("takes the outward code of %j", (input, outward) => {
  expect(outwardCode(input)).toBe(outward);
});

it.each(["", "   "])("asks for a postcode when given %j", (input) => {
  expect(() => outwardCode(input)).toThrow(new PostcodeError("Enter a postcode, such as BS1 or BS1 4DJ."));
});

it.each(["london", "12345", "B", "BS1 4D", "BS1 4DJ 9"])("rejects %j, naming it", (input) => {
  expect(() => outwardCode(input)).toThrow(`"${input.trim()}" doesn't look like a UK postcode. Try the first half, such as BS1.`);
});

it.each([
  ["BT1 1AA", "Northern Ireland"],
  ["gy1 1aa", "Guernsey"],
  ["JE2 3AA", "Jersey"],
  ["IM1 1AA", "Isle of Man"],
])("says %s is outside the grid Gridcast covers", (input, place) => {
  expect(() => outwardCode(input)).toThrow(place);
});

function stubLookup(respond: () => Promise<Response>) {
  const fake = vi.fn<typeof fetch>(() => respond());
  vi.stubGlobal("fetch", fake);
  return fake;
}

function lookupBody(regionid: unknown): Response {
  return new Response(JSON.stringify({ data: [{ regionid, postcode: "BS1" }] }));
}

it("asks NESO about the outward code only and returns its region", async () => {
  const fake = stubLookup(() => Promise.resolve(lookupBody(11)));
  expect(await lookUpRegion("BS1", new AbortController().signal)).toBe(11);
  expect(fake.mock.calls[0]?.[0]).toBe("https://api.carbonintensity.org.uk/regional/postcode/BS1");
});

it.each([
  ["a region outside 1 to 14", () => Promise.resolve(lookupBody(15)), "NESO's lookup gave no region for BS1."],
  ["a textual region", () => Promise.resolve(lookupBody("11")), "NESO's lookup gave no region for BS1."],
  ["no data", () => Promise.resolve(new Response(JSON.stringify({ data: [] }))), "NESO's lookup gave no region for BS1."],
  ["a data entry that is not an object", () => Promise.resolve(new Response(JSON.stringify({ data: [3] }))), "NESO's lookup gave no region for BS1."],
  ["an entry without a region", () => Promise.resolve(new Response(JSON.stringify({ data: [{}] }))), "NESO's lookup gave no region for BS1."],
  ["a body without data", () => Promise.resolve(new Response("null")), "NESO's lookup gave no region for BS1."],
  ["a status other than 200", () => Promise.resolve(new Response("{}", { status: 400 })), "NESO's lookup didn't find BS1, or couldn't be reached."],
  ["a body that is not JSON", () => Promise.resolve(new Response("<html>")), "NESO's lookup didn't find BS1, or couldn't be reached."],
  ["a network failure", () => Promise.reject(new TypeError("Failed to fetch")), "NESO's lookup didn't find BS1, or couldn't be reached."],
])("rejects %s, naming the postcode", async (_case, respond, message) => {
  stubLookup(respond);
  const error: unknown = await lookUpRegion("BS1", new AbortController().signal).catch((reason: unknown) => reason);
  expect(error).toBeInstanceOf(PostcodeLookupError);
  expect((error as PostcodeLookupError).message).toContain(message);
});

it("keeps the cause of a network failure", async () => {
  const cause = new TypeError("Failed to fetch");
  stubLookup(() => Promise.reject(cause));
  const error: unknown = await lookUpRegion("BS1", new AbortController().signal).catch((reason: unknown) => reason);
  expect((error as PostcodeLookupError).cause).toBe(cause);
});

it("gives up after 8 seconds", () => {
  const clock = new AbortController();
  const timeout = vi.spyOn(AbortSignal, "timeout").mockReturnValue(clock.signal);
  const fake = stubLookup(() => new Promise<Response>(() => undefined));
  // The request never settles, so the promise is left pending on purpose.
  void lookUpRegion("BS1", new AbortController().signal);
  expect(timeout).toHaveBeenCalledWith(8_000);
  clock.abort();
  expect(fake.mock.calls[0]?.[1]?.signal?.aborted).toBe(true);
});

it("passes the caller's abort through rather than reporting a failed lookup", async () => {
  const caller = new AbortController();
  const abort = new DOMException("aborted", "AbortError");
  stubLookup(() => Promise.reject(abort));
  caller.abort();
  await expect(lookUpRegion("BS1", caller.signal)).rejects.toBe(abort);
});
