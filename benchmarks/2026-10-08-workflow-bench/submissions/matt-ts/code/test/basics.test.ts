import { describe, expect, it } from "vitest";
import { Scheduler } from "../src/index.js";
import { FakeClock, deferred, flush } from "./helpers.js";

describe("basic lifecycle", () => {
  it("runs a task after start and resolves its result", async () => {
    const clock = new FakeClock();
    const s = new Scheduler({ concurrency: 1, clock });
    s.add({ id: "a", run: async () => 42 });
    expect(s.state("a")).toBe("queued");
    s.start();
    expect(s.state("a")).toBe("running");
    await expect(s.result("a")).resolves.toBe(42);
    expect(s.state("a")).toBe("succeeded");
  });

  it("does not start tasks until start(), and pause stops new starts", async () => {
    const clock = new FakeClock();
    const s = new Scheduler({ concurrency: 1, clock });
    const d = deferred();
    let ran = 0;
    s.add({ id: "a", run: () => { ran++; return d.promise; } });
    s.add({ id: "b", run: async () => { ran++; } });
    await flush();
    expect(ran).toBe(0);
    s.start();
    expect(ran).toBe(1);
    s.pause();
    d.resolve(1);
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(s.state("b")).toBe("queued");
    s.start();
    expect(s.state("b")).toBe("running");
  });

  it("dispatches synchronously from add when started", () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    s.start();
    let ran = false;
    s.add({ id: "a", run: async () => { ran = true; } });
    expect(ran).toBe(true);
  });

  it("treats a synchronous throw like a rejection", async () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    const boom = new Error("boom");
    s.add({ id: "a", run: () => { throw boom; } });
    s.start();
    const err = await s.result("a").catch((e) => e);
    expect(err).toMatchObject({ name: "TaskError", taskId: "a", kind: "failed", attempts: 1, cause: boom });
    expect(s.state("a")).toBe("failed");
  });

  it("throws for unknown ids in state and result, and on duplicate ids", () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    expect(() => s.state("nope")).toThrow(Error);
    expect(() => s.result("nope")).toThrow(Error);
    s.add({ id: "a", run: async () => 1 });
    expect(() => s.add({ id: "a", run: async () => 2 })).toThrow(Error);
  });

  it("rejects invalid concurrency with RangeError", () => {
    for (const concurrency of [0, -1, 1.5, NaN, Infinity]) {
      expect(() => new Scheduler({ concurrency })).toThrow(RangeError);
    }
  });
});
