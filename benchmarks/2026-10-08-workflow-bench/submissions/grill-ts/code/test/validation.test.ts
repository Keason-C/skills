import { describe, expect, it } from "vitest";
import { CycleError, type TaskSpec } from "../src/index.js";
import { setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

const run = async () => 0;

function thrown(fn: () => void): unknown {
  try {
    fn();
  } catch (e) {
    return e;
  }
  return undefined;
}

function cycleOf(fn: () => void): string[] | undefined {
  const error = thrown(fn);
  expect(error).toBeInstanceOf(CycleError);
  return (error as CycleError).cycle;
}

expectNoUnhandledRejections();

describe("dependency cycles", () => {
  it("rejects a self-dependency", () => {
    const { s } = setup();
    expect(cycleOf(() => s.add({ id: "a", deps: ["a"], run }))).toEqual(["a"]);
    expect(() => s.state("a")).toThrow();
  });

  it("lists the cycle from the new task along dependency edges and leaves the scheduler unchanged", async () => {
    const { s, log } = setup();
    s.add({ id: "a", deps: ["b"], run });
    s.add({ id: "b", deps: ["x", "c"], run });
    s.add({ id: "x", run });
    const error = thrown(() => s.add({ id: "c", deps: ["a"], run }));
    expect(error).toBeInstanceOf(CycleError);
    expect((error as CycleError).cycle).toEqual(["c", "a", "b"]);
    expect((error as CycleError).message).toBe("dependency cycle: c -> a -> b");
    expect(() => s.state("c")).toThrow();
    // "c" is still free: adding it without the cycle works, and b's forward reference resolves.
    s.add({ id: "c", run });
    s.start();
    await s.onIdle();
    expect(["a", "b", "c", "x"].map((id) => s.state(id))).toEqual(["succeeded", "succeeded", "succeeded", "succeeded"]);
    expect(log.filter((e) => e[0] === "cancel")).toEqual([]);
  });

  it("detects cycles structurally even through finished tasks", () => {
    const { s } = setup();
    s.add({ id: "x", deps: ["n"], run });
    s.cancel("x");
    expect(cycleOf(() => s.add({ id: "n", deps: ["x"], run }))).toEqual(["n", "x"]);
  });

  it("checks duplicates before cycles", () => {
    const { s } = setup();
    s.add({ id: "a", run });
    const error = thrown(() => s.add({ id: "a", deps: ["a"], run }));
    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(CycleError);
  });
});

describe("input validation", () => {
  const bad: [string, Partial<TaskSpec> & Record<string, unknown>, ErrorConstructor | RangeErrorConstructor][] = [
    ["empty id", { id: "" }, TypeError],
    ["non-string id", { id: 1 as unknown as string }, TypeError],
    ["non-function run", { run: "nope" as unknown as TaskSpec["run"] }, TypeError],
    ["non-array deps", { deps: "a" as unknown as string[] }, TypeError],
    ["non-string dep", { deps: [1 as unknown as string] }, TypeError],
    ["infinite priority", { priority: Infinity }, RangeError],
    ["NaN priority", { priority: NaN }, RangeError],
    ["negative retries", { retries: -1 }, RangeError],
    ["fractional retries", { retries: 1.5 }, RangeError],
    ["negative backoff", { backoffMs: -1 }, RangeError],
    ["infinite backoff", { backoffMs: Infinity }, RangeError],
    ["zero timeout", { timeoutMs: 0 }, RangeError],
    ["infinite timeout", { timeoutMs: Infinity }, RangeError],
  ];

  it.each(bad)("rejects %s", (_name, overrides, ErrorType) => {
    const { s } = setup();
    const spec = { id: "t", run, ...overrides } as TaskSpec;
    expect(() => s.add(spec)).toThrow(ErrorType);
    if (typeof spec.id === "string" && spec.id) expect(() => s.state(spec.id)).toThrow();
  });

  it("accepts negative and fractional priorities", () => {
    const { s } = setup();
    s.add({ id: "a", priority: -3.5, run });
    expect(s.state("a")).toBe("queued");
  });
});
