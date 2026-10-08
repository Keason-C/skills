import { describe, expect, test } from "vitest";
import { TaskError } from "../src/index.js";
import { controlled, instant, scripted, setup, taskError } from "./harness.js";

describe("retries and backoff", () => {
  test("waits backoffMs * 2^(n-1) on the clock after failed attempt n", async () => {
    const { s, clock, take, flush } = setup();
    const e1 = new Error("e1");
    const e2 = new Error("e2");
    const e3 = new Error("e3");
    const a = scripted(s, { id: "A", retries: 2, backoffMs: 100 }, [
      { reject: e1 },
      { reject: e2 },
      { reject: e3 },
    ]);
    s.start();
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["retry", "A", 2, 100, e1]]);
    expect(s.state("A")).toBe("retrying");
    expect(clock.pending()).toEqual([100]);

    await clock.advance(99);
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("retrying");

    await clock.advance(1);
    expect(take()).toEqual([["start", "A", 2], ["retry", "A", 3, 200, e2]]);
    expect(clock.pending()).toEqual([300]);

    await clock.advance(199);
    expect(take()).toEqual([]);
    await clock.advance(1);
    expect(take()).toEqual([
      ["start", "A", 3],
      ["failure", "A", taskError("A", "failed", 3, e3)],
      ["idle"],
    ]);
    expect(s.state("A")).toBe("failed");
    expect(clock.pendingCount()).toBe(0);
    expect(a.calls.map((c) => c.attempt)).toEqual([1, 2, 3]);
    await expect(s.result("A")).rejects.toEqual(taskError("A", "failed", 3, e3));
  });

  test("three retries with backoff 10 wait 10, 20, 40", async () => {
    const { s, clock, take, flush } = setup();
    const err = new Error("x");
    scripted(s, { id: "A", retries: 3, backoffMs: 10 }, [
      { reject: err },
      { reject: err },
      { reject: err },
      { ok: "done" },
    ]);
    s.start();
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["retry", "A", 2, 10, err]]);
    await clock.advance(10);
    expect(take()).toEqual([["start", "A", 2], ["retry", "A", 3, 20, err]]);
    await clock.advance(20);
    expect(take()).toEqual([["start", "A", 3], ["retry", "A", 4, 40, err]]);
    await clock.advance(40);
    expect(take()).toEqual([["start", "A", 4], ["success", "A", "done"], ["idle"]]);
    expect(clock.now()).toBe(70);
    expect(clock.setTimeoutCalls).toBe(3);
    expect(clock.pendingCount()).toBe(0);
  });

  test("a successful retry resolves result with the value", async () => {
    const { s, clock, flush } = setup();
    scripted(s, { id: "A", retries: 1, backoffMs: 5 }, [{ reject: new Error("x") }, { ok: 99 }]);
    s.start();
    const result = s.result<number>("A");
    await flush();
    await clock.advance(5);
    await expect(result).resolves.toBe(99);
    expect(s.state("A")).toBe("succeeded");
  });

  test("retries 0 (default) fails on the first failed attempt with no retry event", async () => {
    const { s, clock, take, flush } = setup();
    const err = new Error("once");
    const a = scripted(s, { id: "A" }, [{ reject: err }]);
    s.start();
    await flush();
    expect(take()).toEqual([
      ["start", "A", 1],
      ["failure", "A", taskError("A", "failed", 1, err)],
      ["idle"],
    ]);
    expect(a.calls).toHaveLength(1);
    expect(clock.setTimeoutCalls).toBe(0);
  });

  test("zero delay: retry event with delayMs 0, no timer, requeued and dispatched in the same reaction", async () => {
    const { s, clock, take, flush } = setup({ concurrency: 2 });
    const err = new Error("x");
    const a = scripted(s, { id: "A", retries: 2 }, [{ reject: err }, { reject: err }, { ok: "v" }]);
    s.start();
    await flush();
    expect(take()).toEqual([
      ["start", "A", 1],
      ["retry", "A", 2, 0, err],
      ["start", "A", 2],
      ["retry", "A", 3, 0, err],
      ["start", "A", 3],
      ["success", "A", "v"],
      ["idle"],
    ]);
    expect(clock.setTimeoutCalls).toBe(0);
    expect(clock.pendingCount()).toBe(0);
    expect(a.calls.map((c) => c.attempt)).toEqual([1, 2, 3]);
  });

  test("zero delay with no free slot: task is queued, not retrying", async () => {
    const { s, clock, take, flush } = setup({ concurrency: 1 });
    const err = new Error("x");
    scripted(s, { id: "A", retries: 1, backoffMs: 0 }, [{ reject: err }, { ok: 1 }]);
    const b = controlled(s, { id: "B" });
    s.start();
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["retry", "A", 2, 0, err], ["start", "B", 1]]);
    expect(s.state("A")).toBe("queued");
    expect(clock.pendingCount()).toBe(0);
    b.resolve(2);
    await flush();
    expect(take()).toEqual([["success", "B", 2], ["start", "A", 2], ["success", "A", 1], ["idle"]]);
  });

  test("each attempt gets its own unaborted signal and a 1-based attempt number", async () => {
    const { s, clock, flush } = setup();
    const a = scripted(s, { id: "A", retries: 1, backoffMs: 1 }, [{ reject: new Error("x") }, { ok: 1 }]);
    s.start();
    await flush();
    await clock.advance(1);
    expect(a.calls).toHaveLength(2);
    const first = a.calls[0];
    const second = a.calls[1];
    expect(first?.attempt).toBe(1);
    expect(second?.attempt).toBe(2);
    expect(first?.signal).toBeInstanceOf(AbortSignal);
    expect(second?.signal).toBeInstanceOf(AbortSignal);
    expect(first?.signal).not.toBe(second?.signal);
    expect(first?.signal.aborted).toBe(false);
    expect(second?.signal.aborted).toBe(false);
  });

  test("the retry event carries the thrown value itself", async () => {
    const { s, take, flush } = setup();
    const token = { reason: "custom" };
    scripted(s, { id: "A", retries: 1, backoffMs: 1 }, [{ reject: token }, { ok: 1 }]);
    s.start();
    await flush();
    const retry = take().find((e) => e[0] === "retry");
    expect(retry?.[4]).toBe(token);
  });

  test("a synchronous throw in run counts as a failed attempt and is retried", async () => {
    const { s, clock, take, flush } = setup();
    const err = new Error("sync");
    scripted(s, { id: "A", retries: 1, backoffMs: 30 }, [{ throw: err }, { ok: "ok" }]);
    s.start();
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["retry", "A", 2, 30, err]]);
    expect(s.state("A")).toBe("retrying");
    await clock.advance(30);
    expect(take()).toEqual([["start", "A", 2], ["success", "A", "ok"], ["idle"]]);
  });

  test("a synchronous throw on the final attempt fails the task with that cause", async () => {
    const { s, take, flush } = setup();
    const err = new Error("sync-final");
    scripted(s, { id: "A" }, [{ throw: err }]);
    s.start();
    await flush();
    expect(take()).toEqual([
      ["start", "A", 1],
      ["failure", "A", taskError("A", "failed", 1, err)],
      ["idle"],
    ]);
    await expect(s.result("A")).rejects.toBeInstanceOf(TaskError);
  });

  test("a run returning a non-promise value succeeds with that value", async () => {
    const { s, take, flush } = setup();
    s.add({ id: "A", run: (() => 5) as unknown as () => Promise<number> });
    s.start();
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["success", "A", 5], ["idle"]]);
    await expect(s.result("A")).resolves.toBe(5);
  });

  test("the failure TaskError reports attempts started and the last attempt's error", async () => {
    const { s, clock, take, flush } = setup();
    const last = new Error("last");
    scripted(s, { id: "A", retries: 1, backoffMs: 1 }, [{ reject: new Error("first") }, { reject: last }]);
    s.start();
    await flush();
    await clock.advance(1);
    const failure = take().find((e) => e[0] === "failure");
    const err = failure?.[2] as TaskError;
    expect(err).toBeInstanceOf(TaskError);
    expect(err.taskId).toBe("A");
    expect(err.kind).toBe("failed");
    expect(err.attempts).toBe(2);
    expect(err.cause).toBe(last);
    await expect(s.result("A")).rejects.toBe(err);
  });

  test("failure in a retrying chain cascades to dependents only at the final failure", async () => {
    const { s, clock, take, flush } = setup({ concurrency: 2 });
    const err = new Error("x");
    scripted(s, { id: "A", retries: 1, backoffMs: 10 }, [{ reject: err }, { reject: err }]);
    const b = instant(s, "B", "b", { deps: ["A"] });
    s.start();
    await flush();
    expect(s.state("B")).toBe("waiting");
    expect(take()).toEqual([["start", "A", 1], ["retry", "A", 2, 10, err]]);
    await clock.advance(10);
    expect(take()).toEqual([
      ["start", "A", 2],
      ["failure", "A", taskError("A", "failed", 2, err)],
      ["cancel", "B", taskError("B", "dependency", 0, expect.any(TaskError))],
      ["idle"],
    ]);
    expect(b.calls).toHaveLength(0);
  });
});
