import { describe, expect, it } from "vitest";
import { TaskError } from "../src/index.js";
import { flush } from "./helpers/fake-clock.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";
import { deferred, setup } from "./helpers/setup.js";

describe("per-attempt timeouts", () => {
  expectNoUnhandledRejections();

  it("times out: aborts the signal, frees the slot at that moment, and ignores the late settle", async () => {
    const { s, clock, log } = setup(1);
    const gate = deferred();
    let signal: AbortSignal | undefined;
    let nextRuns = 0;
    s.add({ id: "slow", timeoutMs: 50, run: (ctx) => ((signal = ctx.signal), gate.promise) });
    s.add({ id: "next", run: () => (nextRuns++, new Promise(() => {})) });
    s.start();
    await clock.advance(49);
    expect(signal?.aborted).toBe(false);
    await clock.advance(1);
    expect(s.state("slow")).toBe("failed");
    expect(nextRuns).toBe(1);
    const error = await s.result("slow").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(TaskError);
    expect(error).toMatchObject({ taskId: "slow", kind: "timeout", attempts: 1, cause: undefined });
    expect(signal?.aborted).toBe(true);
    expect(signal?.reason).toBe(error);
    gate.resolve("too late");
    await flush();
    expect(s.state("slow")).toBe("failed");
    expect(log.filter((e) => e[0] === "success")).toEqual([]);
    expect(clock.pendingCount()).toBe(0);
  });

  it("clears the timeout timer when the attempt settles in time", async () => {
    const { s, clock } = setup();
    s.add({ id: "a", timeoutMs: 50, run: async () => 1 });
    s.start();
    expect(clock.pendingCount()).toBe(1);
    await s.onIdle();
    expect(clock.pendingCount()).toBe(0);
  });

  it("retries a timed-out attempt, passing the same timeout TaskError to retry and the abort reason", async () => {
    const { s, clock, log } = setup();
    const signals: AbortSignal[] = [];
    s.add({
      id: "a",
      timeoutMs: 10,
      retries: 1,
      backoffMs: 5,
      run: (ctx) => (signals.push(ctx.signal), ctx.attempt === 1 ? new Promise(() => {}) : Promise.resolve("ok")),
    });
    s.start();
    await clock.advance(10);
    const retry = log.find((e) => e[0] === "retry")!;
    expect(retry.slice(0, 4)).toEqual(["retry", "a", 2, 5]);
    expect(retry[4]).toMatchObject({ kind: "timeout", attempts: 1 });
    expect(signals[0]!.reason).toBe(retry[4]);
    await clock.advance(5);
    await expect(s.result("a")).resolves.toBe("ok");
    expect(signals[1]!.aborted).toBe(false);
    expect(clock.pendingCount()).toBe(0);
  });

  it("reports kind failed when an earlier attempt timed out but the final one rejected", async () => {
    const { s, clock } = setup();
    const boom = new Error("boom");
    s.add({
      id: "a",
      timeoutMs: 10,
      retries: 1,
      run: (ctx) => (ctx.attempt === 1 ? new Promise(() => {}) : Promise.reject(boom)),
    });
    s.start();
    await clock.advance(10);
    await expect(s.result("a")).rejects.toMatchObject({ kind: "failed", attempts: 2, cause: boom });
    expect(clock.pendingCount()).toBe(0);
  });

  it("ignores a late rejection from a timed-out attempt without an unhandled rejection", async () => {
    const { s, clock } = setup();
    const gate = deferred();
    s.add({ id: "a", timeoutMs: 1, run: () => gate.promise });
    s.start();
    await clock.advance(1);
    gate.reject(new Error("late"));
    await flush();
    await expect(s.result("a")).rejects.toMatchObject({ kind: "timeout" });
  });
});
