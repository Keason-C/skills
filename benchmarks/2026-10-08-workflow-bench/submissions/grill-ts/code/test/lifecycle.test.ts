import { describe, expect, it } from "vitest";
import { flush } from "./helpers/fake-clock.js";
import { Scheduler } from "../src/index.js";
import { deferred, setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

expectNoUnhandledRejections();

describe("scheduler lifecycle", () => {
  it("runs a task after start and resolves its result", async () => {
    const { s, clock } = setup();
    s.add({ id: "a", run: async () => 42 });
    s.start();
    await expect(s.result("a")).resolves.toBe(42);
    expect(s.state("a")).toBe("succeeded");
    expect(clock.pendingCount()).toBe(0);
  });

  it("starts paused: nothing runs until start(), then dispatch is synchronous", () => {
    const { s } = setup();
    let runs = 0;
    s.add({ id: "a", run: async () => void runs++ });
    expect(runs).toBe(0);
    expect(s.state("a")).toBe("queued");
    s.start();
    expect(runs).toBe(1);
    expect(s.state("a")).toBe("running");
    s.add({ id: "b", run: async () => void runs++ });
    expect(s.state("b")).toBe("queued");
  });

  it.each([0, -1, 1.5, NaN, Infinity])("rejects concurrency %s with a RangeError", (concurrency) => {
    expect(() => new Scheduler({ concurrency })).toThrow(RangeError);
  });

  it("never runs more than `concurrency` tasks and fills a freed slot from the settle reaction", async () => {
    const { s } = setup(2);
    const gates = { a: deferred(), b: deferred(), c: deferred() };
    for (const id of ["a", "b", "c"] as const) s.add({ id, run: () => gates[id].promise });
    s.start();
    expect(["a", "b", "c"].map((id) => s.state(id))).toEqual(["running", "running", "queued"]);
    gates.a.resolve(1);
    await flush();
    expect(["a", "b", "c"].map((id) => s.state(id))).toEqual(["succeeded", "running", "running"]);
  });

  it("pause() stops new starts but lets running tasks finish; start() resumes", async () => {
    const { s } = setup(1);
    const gate = deferred();
    let bRuns = 0;
    s.add({ id: "a", run: () => gate.promise });
    s.add({ id: "b", run: async () => void bRuns++ });
    s.start();
    s.pause();
    s.pause();
    gate.resolve("done");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(s.state("b")).toBe("queued");
    expect(bRuns).toBe(0);
    s.start();
    s.start();
    expect(bRuns).toBe(1);
  });

  it("throws for unknown ids in state() and result(), and for duplicate ids in add()", () => {
    const { s } = setup();
    expect(() => s.state("nope")).toThrow(Error);
    expect(() => s.result("nope")).toThrow(Error);
    s.add({ id: "a", run: async () => 1 });
    expect(() => s.add({ id: "a", run: async () => 2 })).toThrow(Error);
    expect(s.state("a")).toBe("queued");
  });
});
