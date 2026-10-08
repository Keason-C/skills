import { describe, expect, it } from "vitest";
import { CycleError, Scheduler, type TaskContext } from "../src/index.js";
import { FakeClock, deferred, flush } from "./helpers.js";

const make = (concurrency = 4) => {
  const s = new Scheduler({ concurrency, clock: new FakeClock() });
  s.start();
  return s;
};

describe("dependencies", () => {
  it("waits for deps to succeed and passes their values in ctx.deps", async () => {
    const s = make();
    const a = deferred<number>();
    let seen: TaskContext | undefined;
    s.add({ id: "a", run: () => a.promise });
    s.add({ id: "b", run: async () => "B" });
    s.add({ id: "c", deps: ["a", "b"], run: async (ctx) => { seen = ctx; return "C"; } });
    expect(s.state("c")).toBe("waiting");
    await flush();
    expect(s.state("c")).toBe("waiting");
    a.resolve(1);
    await expect(s.result("c")).resolves.toBe("C");
    expect(seen?.deps).toEqual({ a: 1, b: "B" });
    expect(seen?.attempt).toBe(1);
    expect(seen?.signal).toBeInstanceOf(AbortSignal);
  });

  it("supports forward references to tasks added later", async () => {
    const s = make();
    s.add({ id: "late-user", deps: ["late"], run: async (ctx) => ctx.deps.late });
    expect(s.state("late-user")).toBe("waiting");
    await flush();
    expect(s.state("late-user")).toBe("waiting");
    s.add({ id: "late", run: async () => "x" });
    await expect(s.result("late-user")).resolves.toBe("x");
  });

  it("starts a task during add when its deps already succeeded", async () => {
    const s = make();
    s.add({ id: "a", run: async () => 1 });
    await s.result("a");
    let ran = false;
    s.add({ id: "b", deps: ["a"], run: async () => { ran = true; } });
    expect(ran).toBe(true);
  });

  it("rejects a self-dependency with a CycleError and leaves the scheduler unchanged", () => {
    const s = make();
    let error: unknown;
    try {
      s.add({ id: "a", deps: ["a"], run: async () => 1 });
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(CycleError);
    expect((error as CycleError).cycle).toEqual(["a"]);
    expect(() => s.state("a")).toThrow();
    s.add({ id: "a", run: async () => 1 });
  });

  it("rejects a longer cycle, listing exactly the ids on it", () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    s.add({ id: "x", run: async () => 0 });
    s.add({ id: "a", deps: ["b", "x"], run: async () => 1 });
    s.add({ id: "b", deps: ["c"], run: async () => 1 });
    let error: unknown;
    try {
      s.add({ id: "c", deps: ["x", "a"], run: async () => 1 });
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(CycleError);
    expect([...(error as CycleError).cycle].sort()).toEqual(["a", "b", "c"]);
    expect(() => s.state("c")).toThrow();
    expect(s.state("b")).toBe("waiting");
  });
});
