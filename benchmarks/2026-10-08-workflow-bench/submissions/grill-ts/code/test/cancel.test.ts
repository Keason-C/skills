import { describe, expect, it } from "vitest";
import { TaskError } from "../src/index.js";
import { flush } from "./helpers/fake-clock.js";
import { deferred, setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

const errorOf = (p: Promise<unknown>) => p.catch((e: unknown) => e);

expectNoUnhandledRejections();

describe("cancellation", () => {
  it("cancels a running task: aborts with the cancel error, frees the slot immediately, ignores the late settle", async () => {
    const { s, clock, log } = setup(1);
    const gate = deferred();
    let signal: AbortSignal | undefined;
    let nextRuns = 0;
    s.add({ id: "a", timeoutMs: 100, run: (ctx) => ((signal = ctx.signal), gate.promise) });
    s.add({ id: "b", run: async () => void nextRuns++ });
    s.start();
    const reason = new Error("stop");
    expect(s.cancel("a", reason)).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    expect(nextRuns).toBe(1);
    expect(clock.pendingCount()).toBe(0);
    const error = await errorOf(s.result("a"));
    expect(error).toBeInstanceOf(TaskError);
    expect(error).toMatchObject({ taskId: "a", kind: "cancelled", attempts: 1, cause: reason });
    expect(signal?.reason).toBe(error);
    gate.resolve("late");
    await flush();
    expect(s.state("a")).toBe("cancelled");
    expect(log).toEqual([
      ["start", "a", 1],
      ["cancel", "a", error],
      ["start", "b", 1],
      ["success", "b", undefined],
      ["idle"],
    ]);
  });

  it("cancels waiting and queued tasks so their run never starts", async () => {
    const { s } = setup(1);
    let runs = 0;
    s.add({ id: "queued", run: async () => void runs++ });
    s.add({ id: "waiting", deps: ["never-added"], run: async () => void runs++ });
    expect(s.cancel("queued")).toBe(true);
    expect(s.cancel("waiting")).toBe(true);
    s.start();
    await s.onIdle();
    expect(runs).toBe(0);
    await expect(s.result("queued")).rejects.toMatchObject({ kind: "cancelled", attempts: 0, cause: undefined });
  });

  it("cancels a retrying task and clears its backoff timer", async () => {
    const { s, clock } = setup();
    s.add({ id: "a", retries: 1, backoffMs: 50, run: async () => Promise.reject(new Error("x")) });
    s.start();
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(s.cancel("a")).toBe(true);
    expect(clock.pendingCount()).toBe(0);
    await expect(s.result("a")).rejects.toMatchObject({ kind: "cancelled", attempts: 1 });
  });

  it("returns false for finished and unknown tasks", async () => {
    const { s } = setup();
    s.add({ id: "a", run: async () => 1 });
    s.start();
    await s.onIdle();
    expect(s.cancel("a")).toBe(false);
    expect(s.cancel("nope")).toBe(false);
    expect(s.cancel("a")).toBe(false);
    expect(s.state("a")).toBe("succeeded");
  });

  it("cascades to dependents with kind dependency, after the task's own cancel event", async () => {
    const { s, log } = setup();
    s.add({ id: "child", deps: ["a"], run: async () => 0 });
    s.add({ id: "a", run: async () => 0 });
    s.cancel("a", "why");
    const aErr = await errorOf(s.result("a"));
    const childErr = await errorOf(s.result("child"));
    expect(childErr).toMatchObject({ kind: "dependency", attempts: 0, cause: aErr });
    expect(log).toEqual([["cancel", "a", aErr], ["cancel", "child", childErr], ["idle"]]);
  });

  it("does not invoke run when a start listener cancels the task; the attempt still counts", async () => {
    const { s, clock } = setup();
    let runs = 0;
    s.on("start", (id) => void s.cancel(id));
    s.add({ id: "a", timeoutMs: 10, run: async () => void runs++ });
    s.start();
    expect(runs).toBe(0);
    expect(clock.pendingCount()).toBe(0);
    await expect(s.result("a")).rejects.toMatchObject({ kind: "cancelled", attempts: 1 });
  });
});
