import { afterEach, describe, expect, test, vi } from "vitest";
import { controlled, instant, scripted, setup } from "./harness.js";

describe("no real timers or wall clock", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("a scenario with retries, timeouts and cancels touches no global timer or Date.now", async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout");
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");
    const setImmediateSpy = vi.spyOn(globalThis, "setImmediate");
    const dateNowSpy = vi.spyOn(Date, "now");

    const { s, clock, flush } = setup({ concurrency: 2 });
    scripted(s, { id: "retry", retries: 2, backoffMs: 10 }, [
      { reject: new Error("a") },
      { reject: new Error("b") },
      { ok: 1 },
    ]);
    controlled(s, { id: "timeout", timeoutMs: 5, retries: 1, backoffMs: 1 });
    const cancelled = controlled(s, { id: "cancelled", timeoutMs: 50 });
    instant(s, "dep", "d", { deps: ["retry"] });
    s.start();
    await flush();
    await clock.advance(5);
    s.cancel("cancelled");
    cancelled.resolve("late");
    await clock.advance(100);
    await s.onIdle();

    expect([s.state("retry"), s.state("timeout"), s.state("cancelled"), s.state("dep")]).toEqual([
      "succeeded",
      "failed",
      "cancelled",
      "succeeded",
    ]);
    expect(setTimeoutSpy).not.toHaveBeenCalled();
    expect(setIntervalSpy).not.toHaveBeenCalled();
    expect(setImmediateSpy).not.toHaveBeenCalled();
    expect(dateNowSpy).not.toHaveBeenCalled();
    expect(clock.pendingCount()).toBe(0);
  });
});

describe("timer accounting on the fake clock", () => {
  test("a success-only run creates no timers at all", async () => {
    const { s, clock, flush } = setup({ concurrency: 2 });
    instant(s, "A", 1);
    instant(s, "B", 2, { deps: ["A"] });
    instant(s, "C", 3);
    s.start();
    await flush();
    expect(s.state("B")).toBe("succeeded");
    expect(clock.setTimeoutCalls).toBe(0);
    expect(clock.pendingCount()).toBe(0);
  });

  test("a retrying task has exactly one pending timer, due at now + delay", async () => {
    const { s, clock, flush } = setup();
    await clock.advance(1000);
    scripted(s, { id: "A", retries: 1, backoffMs: 25 }, [{ reject: new Error("x") }, { ok: 1 }]);
    s.start();
    await flush();
    expect(clock.pending()).toEqual([1025]);
    await clock.advance(25);
    expect(clock.pendingCount()).toBe(0);
    expect(clock.setTimeoutCalls).toBe(1);
  });

  test("a running attempt with a timeout has exactly one pending timer", async () => {
    const { s, clock, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A", timeoutMs: 30 });
    controlled(s, { id: "B" });
    s.start();
    expect(clock.pending()).toEqual([30]);
    a.resolve(1);
    await flush();
    expect(clock.pendingCount()).toBe(0);
    expect(clock.setTimeoutCalls).toBe(1);
  });

  test("retries with timeouts: one timer per attempt plus one per backoff, none left over", async () => {
    const { s, clock } = setup();
    controlled(s, { id: "A", timeoutMs: 10, retries: 2, backoffMs: 1 });
    s.start();
    await clock.advance(10);
    expect(clock.pending()).toEqual([11]);
    await clock.advance(1);
    expect(clock.pending()).toEqual([21]);
    await clock.advance(10);
    expect(clock.pending()).toEqual([23]);
    await clock.advance(2);
    expect(clock.pending()).toEqual([33]);
    await clock.advance(10);
    expect(s.state("A")).toBe("failed");
    expect(clock.pendingCount()).toBe(0);
    expect(clock.setTimeoutCalls).toBe(5);
  });

  test("cancelling a retrying task and a running task with a timeout leaves no timers", async () => {
    const { s, clock, flush } = setup({ concurrency: 2 });
    scripted(s, { id: "R", retries: 1, backoffMs: 100 }, [{ reject: new Error("x") }, { ok: 1 }]);
    controlled(s, { id: "T", timeoutMs: 100 });
    s.start();
    await flush();
    expect(clock.pendingCount()).toBe(2);
    s.cancel("R");
    expect(clock.pendingCount()).toBe(1);
    s.cancel("T");
    expect(clock.pendingCount()).toBe(0);
    await clock.advance(100);
    expect([s.state("R"), s.state("T")]).toEqual(["cancelled", "cancelled"]);
  });

  test("a cascade from a timeout clears nothing it should keep and leaves no timers", async () => {
    const { s, clock } = setup({ concurrency: 3 });
    controlled(s, { id: "A", timeoutMs: 10 });
    const b = controlled(s, { id: "B", timeoutMs: 100 });
    controlled(s, { id: "C", deps: ["A"], timeoutMs: 5 });
    s.start();
    expect(clock.pending()).toEqual([10, 100]);
    await clock.advance(10);
    expect(clock.pending()).toEqual([100]);
    expect(s.state("C")).toBe("cancelled");
    b.resolve(1);
    await clock.advance(0);
    expect(clock.pendingCount()).toBe(0);
  });

  test("a task that times out on its last retry leaves no timers and no late events", async () => {
    const { s, clock, take } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 10, retries: 1, backoffMs: 5 });
    s.start();
    await clock.advance(10 + 5 + 10);
    expect(s.state("A")).toBe("failed");
    expect(clock.pendingCount()).toBe(0);
    take();
    a.resolve("late 1", 1);
    a.resolve("late 2", 2);
    await clock.advance(1000);
    expect(take()).toEqual([]);
  });
});
