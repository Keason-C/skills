import { describe, expect, test } from "vitest";
import { TaskError } from "../src/index.js";
import { controlled, setup, taskError } from "./harness.js";

describe("timeouts", () => {
  test("an attempt still running after timeoutMs fails with kind timeout", async () => {
    const { s, clock, take, flush } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 50 });
    s.start();
    expect(clock.pending()).toEqual([50]);
    await clock.advance(49);
    expect(s.state("A")).toBe("running");
    expect(take()).toEqual([["start", "A", 1]]);
    await clock.advance(1);
    expect(s.state("A")).toBe("failed");
    const [failure, idle] = take();
    expect(idle).toEqual(["idle"]);
    expect(failure).toEqual(["failure", "A", taskError("A", "timeout", 1, undefined)]);
    const err = failure?.[2] as TaskError;
    expect(err).toBeInstanceOf(TaskError);
    const signal = a.ctx().signal;
    expect(signal.aborted).toBe(true);
    expect(signal.reason).toBe(err);
    await expect(s.result("A")).rejects.toBe(err);
    expect(clock.pendingCount()).toBe(0);
    await flush();
    expect(take()).toEqual([]);
  });

  test("the timeout timer is cleared when the attempt settles first", async () => {
    const { s, clock, take, flush } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 50 });
    s.start();
    expect(clock.pendingCount()).toBe(1);
    a.resolve("v");
    await flush();
    expect(clock.pendingCount()).toBe(0);
    expect(take()).toEqual([["start", "A", 1], ["success", "A", "v"], ["idle"]]);
    await clock.advance(1000);
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("succeeded");
    expect(a.ctx().signal.aborted).toBe(false);
  });

  test("the timeout timer is cleared when the attempt rejects first", async () => {
    const { s, clock, flush } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 50 });
    s.start();
    a.reject(new Error("x"));
    await flush();
    expect(clock.pendingCount()).toBe(0);
    expect(s.state("A")).toBe("failed");
    await expect(s.result("A")).rejects.toEqual(taskError("A", "failed", 1, expect.any(Error)));
  });

  test("a timeout releases the slot at that moment", async () => {
    const { s, clock, take } = setup({ concurrency: 1 });
    controlled(s, { id: "A", timeoutMs: 10 });
    const b = controlled(s, { id: "B" });
    s.start();
    take();
    expect(clock.fireNextSync()).toBe(true);
    expect(b.calls).toHaveLength(1);
    expect(take()).toEqual([
      ["failure", "A", taskError("A", "timeout", 1, undefined)],
      ["start", "B", 1],
    ]);
    expect(s.state("B")).toBe("running");
  });

  test("a late resolve from a timed-out attempt is ignored", async () => {
    const { s, clock, take, flush } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 10 });
    s.start();
    await clock.advance(10);
    take();
    a.resolve("late");
    await flush();
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("failed");
    await expect(s.result("A")).rejects.toEqual(taskError("A", "timeout", 1, undefined));
  });

  test("a late reject from a timed-out attempt is ignored", async () => {
    const { s, clock, take, flush } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 10 });
    s.start();
    await clock.advance(10);
    take();
    a.reject(new Error("late"));
    await flush();
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("failed");
  });

  test("a timeout is a failed attempt: retried with the timeout TaskError as the retry error", async () => {
    const { s, clock, take, flush } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 10, retries: 1, backoffMs: 5 });
    s.start();
    await clock.advance(10);
    const [, retry] = take();
    expect(retry).toEqual(["retry", "A", 2, 5, taskError("A", "timeout", 1, undefined)]);
    const timeoutErr = retry?.[4];
    expect(timeoutErr).toBeInstanceOf(TaskError);
    expect(a.ctx(1).signal.reason).toBe(timeoutErr);
    expect(s.state("A")).toBe("retrying");
    expect(clock.pending()).toEqual([15]);
    await clock.advance(5);
    expect(take()).toEqual([["start", "A", 2]]);
    expect(a.ctx(2).attempt).toBe(2);
    expect(a.ctx(2).signal.aborted).toBe(false);
    expect(clock.pending()).toEqual([25]);
    a.resolve("second");
    await flush();
    expect(take()).toEqual([["success", "A", "second"], ["idle"]]);
    expect(clock.pendingCount()).toBe(0);
    await expect(s.result("A")).resolves.toBe("second");
  });

  test("final attempt timing out gives kind timeout with attempts = total attempts", async () => {
    const { s, clock, take } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 10, retries: 1, backoffMs: 1 });
    s.start();
    await clock.advance(10);
    await clock.advance(1);
    take();
    await clock.advance(10);
    const [failure] = take();
    expect(failure).toEqual(["failure", "A", taskError("A", "timeout", 2, undefined)]);
    const err = failure?.[2];
    expect(a.ctx(2).signal.reason).toBe(err);
    await expect(s.result("A")).rejects.toBe(err);
    expect(clock.pendingCount()).toBe(0);
  });

  test("a timed-out attempt followed by an ordinary final failure gives kind failed", async () => {
    const { s, clock, take, flush } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 10, retries: 1, backoffMs: 1 });
    s.start();
    await clock.advance(11);
    take();
    const err = new Error("real");
    a.reject(err);
    await flush();
    expect(take()).toEqual([["failure", "A", taskError("A", "failed", 2, err)], ["idle"]]);
  });

  test("the timeout timer starts when the attempt starts, not when the task is queued", async () => {
    const { s, clock, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B", timeoutMs: 10 });
    s.start();
    expect(clock.pendingCount()).toBe(0);
    await clock.advance(100);
    expect(s.state("B")).toBe("queued");
    a.resolve(1);
    await flush();
    expect(clock.pending()).toEqual([110]);
    await clock.advance(9);
    expect(s.state("B")).toBe("running");
    await clock.advance(1);
    expect(s.state("B")).toBe("failed");
    expect(take()).toEqual([
      ["start", "A", 1],
      ["success", "A", 1],
      ["start", "B", 1],
      ["failure", "B", taskError("B", "timeout", 1, undefined)],
      ["idle"],
    ]);
    expect(b.ctx().signal.aborted).toBe(true);
  });

  test("within the failure listener the state is already failed and the signal already aborted", async () => {
    const { s, clock } = setup();
    const a = controlled(s, { id: "A", timeoutMs: 10 });
    const observed: Array<[string, boolean]> = [];
    s.on("failure", (id) => {
      observed.push([s.state(id), a.ctx().signal.aborted]);
    });
    s.start();
    await clock.advance(10);
    expect(observed).toEqual([["failed", true]]);
  });

  test("a timeout cascades to dependents with kind dependency", async () => {
    const { s, clock, take } = setup({ concurrency: 2 });
    controlled(s, { id: "A", timeoutMs: 10 });
    const b = controlled(s, { id: "B", deps: ["A"] });
    s.start();
    take();
    await clock.advance(10);
    const [failure, cancel, idle] = take();
    expect(failure).toEqual(["failure", "A", taskError("A", "timeout", 1, undefined)]);
    expect(cancel).toEqual(["cancel", "B", taskError("B", "dependency", 0, failure?.[2])]);
    expect(idle).toEqual(["idle"]);
    expect(b.calls).toHaveLength(0);
  });
});
