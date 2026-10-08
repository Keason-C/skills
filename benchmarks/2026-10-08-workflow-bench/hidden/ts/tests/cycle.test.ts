import { describe, expect, it } from "vitest";
import { CycleError } from "../src/index.js";
import { flush, make } from "./helpers.js";

function catchCycle(fn: () => void): CycleError {
  let caught: unknown;
  try {
    fn();
  } catch (e) {
    caught = e;
  }
  expect(caught).toBeInstanceOf(CycleError);
  return caught as CycleError;
}

describe("dependency cycles", () => {
  it("a task depending on itself is rejected with a CycleError and not added", () => {
    const { s, runs } = make(1);
    const err = catchCycle(() => s.add(runs.task("a", { deps: ["a"] })));
    expect(err).toBeInstanceOf(Error);
    expect(new Set(err.cycle)).toEqual(new Set(["a"]));
    expect(() => s.state("a")).toThrow();
  });

  it("closing a two-task cycle through a forward reference throws; the new task is not added", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a", { deps: ["b"] }));
    const err = catchCycle(() => s.add(runs.task("b", { deps: ["a"] })));
    expect(new Set(err.cycle)).toEqual(new Set(["a", "b"]));
    expect(() => s.state("b")).toThrow();
    expect(s.state("a")).toBe("waiting");
  });

  it("a three-task cycle lists all three ids", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a", { deps: ["b"] }));
    s.add(runs.task("b", { deps: ["c"] }));
    const err = catchCycle(() => s.add(runs.task("c", { deps: ["a"] })));
    expect(new Set(err.cycle)).toEqual(new Set(["a", "b", "c"]));
    expect(() => s.state("c")).toThrow();
  });

  it("ids that are not on the cycle are not listed", () => {
    const { s, runs } = make(1);
    s.add(runs.task("x", { deps: ["a"] })); // depends on the cycle but is not on it
    s.add(runs.task("a", { deps: ["b"] }));
    s.add(runs.task("z"));
    const err = catchCycle(() => s.add(runs.task("b", { deps: ["z", "a"] })));
    expect(new Set(err.cycle)).toEqual(new Set(["a", "b"]));
  });

  it("the scheduler is unchanged after a rejected add: the id can be added later and work proceeds", async () => {
    const { s, runs, log } = make(2, { events: true });
    s.add(runs.task("a", { deps: ["b"] }));
    s.start();
    const before = log.length;
    catchCycle(() => s.add(runs.task("b", { deps: ["a"] })));
    expect(log.length).toBe(before);
    expect(runs.calls.length).toBe(0);
    s.add(runs.task("b"));
    expect(s.state("b")).toBe("running");
    runs.resolve("b", "B");
    await flush();
    expect(s.state("a")).toBe("running");
    expect(runs.last("a").ctx.deps).toEqual({ b: "B" });
  });

  it("a rejected self-dependent id can be re-added without the self-dependency", () => {
    const { s, runs } = make(1);
    catchCycle(() => s.add(runs.task("a", { deps: ["a"] })));
    expect(() => s.add(runs.task("a"))).not.toThrow();
    expect(s.state("a")).toBe("queued");
  });

  it("diamonds and shared dependencies are not cycles", () => {
    const { s, runs } = make(1);
    s.add(runs.task("d", { deps: ["b", "c"] }));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c", { deps: ["a", "b"] }));
    expect(() => s.add(runs.task("a"))).not.toThrow();
    expect(s.state("a")).toBe("queued");
    expect(s.state("d")).toBe("waiting");
  });

  it("a cycle on a started scheduler starts nothing", async () => {
    const { s, runs } = make(2);
    s.start();
    s.add(runs.task("p", { deps: ["q"] }));
    catchCycle(() => s.add(runs.task("q", { deps: ["p"] })));
    await flush();
    expect(runs.calls.length).toBe(0);
    expect(s.state("p")).toBe("waiting");
  });
});
