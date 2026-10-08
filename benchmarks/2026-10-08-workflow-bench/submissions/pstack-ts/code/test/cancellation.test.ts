import { describe, expect, test } from "vitest";
import { TaskError } from "../src/index.js";
import { controlled, instant, scripted, setup, taskError } from "./harness.js";

const noop = () => Promise.resolve(undefined);

describe("cancel by state", () => {
  test("waiting: returns true, attempts 0, cause is the reason", async () => {
    const { s, take, flush } = setup();
    const b = controlled(s, { id: "B", deps: ["A"] });
    const reason = new Error("why");
    expect(s.cancel("B", reason)).toBe(true);
    expect(s.state("B")).toBe("cancelled");
    expect(take()).toEqual([["cancel", "B", taskError("B", "cancelled", 0, reason)], ["idle"]]);
    await expect(s.result("B")).rejects.toEqual(taskError("B", "cancelled", 0, reason));
    instant(s, "A");
    s.start();
    await flush();
    expect(b.calls).toHaveLength(0);
    expect(s.state("B")).toBe("cancelled");
  });

  test("queued: returns true, attempts 0, run never invoked", async () => {
    const { s, take, flush } = setup();
    const a = controlled(s, { id: "A" });
    expect(s.cancel("A")).toBe(true);
    expect(take()).toEqual([["cancel", "A", taskError("A", "cancelled", 0, undefined)], ["idle"]]);
    s.start();
    await flush();
    expect(a.calls).toHaveLength(0);
    expect(take()).toEqual([]);
  });

  test("running: aborts the signal with the TaskError (not the raw reason) and releases the slot", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    s.start();
    take();
    const reason = "stop now";
    expect(s.cancel("A", reason)).toBe(true);
    const [cancel, start] = take();
    expect(cancel).toEqual(["cancel", "A", taskError("A", "cancelled", 1, reason)]);
    expect(start).toEqual(["start", "B", 1]);
    const err = cancel?.[2] as TaskError;
    expect(err).toBeInstanceOf(TaskError);
    const signal = a.ctx().signal;
    expect(signal.aborted).toBe(true);
    expect(signal.reason).toBe(err);
    expect(b.calls).toHaveLength(1);
    await expect(s.result("A")).rejects.toBe(err);
    await flush();
    expect(take()).toEqual([]);
  });

  test("running: a late resolve is ignored", async () => {
    const { s, take, flush } = setup();
    const a = controlled(s, { id: "A" });
    s.start();
    s.cancel("A");
    take();
    a.resolve("late");
    await flush();
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("cancelled");
    await expect(s.result("A")).rejects.toEqual(taskError("A", "cancelled", 1, undefined));
  });

  test("running: a late reject is ignored", async () => {
    const { s, take, flush } = setup();
    const a = controlled(s, { id: "A", retries: 3, backoffMs: 10 });
    s.start();
    s.cancel("A");
    take();
    a.reject(new Error("late"));
    await flush();
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("cancelled");
  });

  test("running with a timeout: the timeout timer is cleared", async () => {
    const { s, clock, take } = setup();
    controlled(s, { id: "A", timeoutMs: 100 });
    s.start();
    expect(clock.pendingCount()).toBe(1);
    expect(s.cancel("A")).toBe(true);
    expect(clock.pendingCount()).toBe(0);
    take();
    await clock.advance(100);
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("cancelled");
  });

  test("retrying: returns true, clears the backoff timer, attempts counts the started attempts", async () => {
    const { s, clock, take, flush } = setup();
    scripted(s, { id: "A", retries: 2, backoffMs: 100 }, [{ reject: new Error("x") }, { ok: 1 }, { ok: 1 }]);
    s.start();
    await flush();
    expect(s.state("A")).toBe("retrying");
    expect(clock.pendingCount()).toBe(1);
    take();
    expect(s.cancel("A", "r")).toBe(true);
    expect(clock.pendingCount()).toBe(0);
    expect(s.state("A")).toBe("cancelled");
    expect(take()).toEqual([["cancel", "A", taskError("A", "cancelled", 1, "r")], ["idle"]]);
    await clock.advance(100);
    expect(take()).toEqual([]);
  });

  test("succeeded, failed and cancelled tasks return false with no events", async () => {
    const { s, take, flush } = setup({ concurrency: 3 });
    instant(s, "OK");
    scripted(s, { id: "BAD" }, [{ reject: new Error("x") }]);
    s.add({ id: "GONE", run: noop });
    s.cancel("GONE");
    s.start();
    await flush();
    take();
    expect(s.cancel("OK")).toBe(false);
    expect(s.cancel("BAD")).toBe(false);
    expect(s.cancel("GONE")).toBe(false);
    await flush();
    expect(take()).toEqual([]);
    expect([s.state("OK"), s.state("BAD"), s.state("GONE")]).toEqual(["succeeded", "failed", "cancelled"]);
  });

  test("unknown id returns false and does not throw", () => {
    const { s, take } = setup();
    expect(s.cancel("nope")).toBe(false);
    expect(s.cancel("nope", "reason")).toBe(false);
    expect(take()).toEqual([]);
  });

  test("reason omitted gives cause undefined", async () => {
    const { s } = setup();
    s.add({ id: "A", run: noop });
    s.cancel("A");
    const err = await s.result("A").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(TaskError);
    expect((err as TaskError).cause).toBeUndefined();
    expect(Object.hasOwn(err as object, "cause")).toBe(true);
  });

  test("inside the cancel listener the state is cancelled and the signal aborted", () => {
    const { s } = setup();
    const a = controlled(s, { id: "A" });
    const observed: Array<[string, boolean]> = [];
    s.on("cancel", (id) => {
      observed.push([s.state(id), a.ctx().signal.aborted]);
    });
    s.start();
    s.cancel("A");
    expect(observed).toEqual([["cancelled", true]]);
  });
});

describe("cascade", () => {
  test("cancel cascades to transitive dependents in add order with direct-dependency causes", async () => {
    const { s, take, flush } = setup({ concurrency: 4 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B", deps: ["A"] });
    const c = controlled(s, { id: "C", deps: ["B"] });
    const d = controlled(s, { id: "D", deps: ["A"] });
    const e = controlled(s, { id: "E" });
    s.start();
    take();
    expect(s.cancel("A", "root")).toBe(true);
    const events = take();
    expect(events).toEqual([
      ["cancel", "A", taskError("A", "cancelled", 1, "root")],
      ["cancel", "B", taskError("B", "dependency", 0, expect.any(TaskError))],
      ["cancel", "C", taskError("C", "dependency", 0, expect.any(TaskError))],
      ["cancel", "D", taskError("D", "dependency", 0, expect.any(TaskError))],
    ]);
    const errOf = (id: string) => events.find((ev) => ev[1] === id)?.[2];
    expect((errOf("B") as TaskError).cause).toBe(errOf("A"));
    expect((errOf("C") as TaskError).cause).toBe(errOf("B"));
    expect((errOf("D") as TaskError).cause).toBe(errOf("A"));
    expect([s.state("B"), s.state("C"), s.state("D"), s.state("E")]).toEqual([
      "cancelled",
      "cancelled",
      "cancelled",
      "running",
    ]);
    await expect(s.result("C")).rejects.toBe(errOf("C"));
    expect(b.calls.length + c.calls.length + d.calls.length).toBe(0);
    e.resolve(1);
    await flush();
    expect(take()).toEqual([["success", "E", 1], ["idle"]]);
    expect(a.calls).toHaveLength(1);
  });

  test("cascade events follow add order even when the dependency chain reaches them later", () => {
    const { s, take } = setup();
    s.add({ id: "A", run: noop });
    s.add({ id: "C", run: noop, deps: ["B"] });
    s.add({ id: "B", run: noop, deps: ["A"] });
    s.cancel("A");
    const events = take();
    expect(events.map((ev) => ev.slice(0, 2))).toEqual([["cancel", "A"], ["cancel", "C"], ["cancel", "B"], ["idle"]]);
    const errOf = (id: string) => events.find((ev) => ev[1] === id)?.[2] as TaskError;
    expect(errOf("C").cause).toBe(errOf("B"));
    expect(errOf("B").cause).toBe(errOf("A"));
    expect(errOf("C").kind).toBe("dependency");
  });

  test("a failure cascades with the failure TaskError as the direct cause", async () => {
    const { s, take, flush } = setup();
    const boom = new Error("boom");
    scripted(s, { id: "A" }, [{ reject: boom }]);
    const b = controlled(s, { id: "B", deps: ["A"] });
    s.start();
    await flush();
    const events = take();
    expect(events).toEqual([
      ["start", "A", 1],
      ["failure", "A", taskError("A", "failed", 1, boom)],
      ["cancel", "B", taskError("B", "dependency", 0, expect.any(TaskError))],
      ["idle"],
    ]);
    expect((events[2]?.[2] as TaskError).cause).toBe(events[1]?.[2]);
    expect(b.calls).toHaveLength(0);
    await expect(s.result("B")).rejects.toMatchObject({ kind: "dependency", attempts: 0 });
  });

  test("with several paths the cause comes from the breadth-first nearest dependency", () => {
    const { s, take } = setup();
    s.add({ id: "A", run: noop });
    s.add({ id: "B", run: noop, deps: ["A"] });
    s.add({ id: "C", run: noop, deps: ["B", "A"] });
    s.cancel("A");
    const events = take();
    const errOf = (id: string) => events.find((ev) => ev[1] === id)?.[2] as TaskError;
    expect(events.map((ev) => ev.slice(0, 2))).toEqual([["cancel", "A"], ["cancel", "B"], ["cancel", "C"], ["idle"]]);
    expect(errOf("C").cause).toBe(errOf("A"));
  });

  test("cancelling a dependent does not affect its dependency or siblings", async () => {
    const { s, take, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A" });
    controlled(s, { id: "B", deps: ["A"] });
    const c = controlled(s, { id: "C", deps: ["A"] });
    s.start();
    take();
    expect(s.cancel("B")).toBe(true);
    expect(take()).toEqual([["cancel", "B", taskError("B", "cancelled", 0, undefined)]]);
    expect(s.state("A")).toBe("running");
    a.resolve(1);
    await flush();
    expect(take()).toEqual([["success", "A", 1], ["start", "C", 1]]);
    expect(c.ctx().deps).toEqual({ A: 1 });
  });

  test("a forward-referenced dependency added after the cascade runs normally", async () => {
    const { s, take, flush } = setup();
    s.add({ id: "A", run: noop, deps: ["Z"] });
    s.add({ id: "B", run: noop, deps: ["A"] });
    s.cancel("A");
    take();
    s.start();
    instant(s, "Z", "z");
    await flush();
    expect(take()).toEqual([["start", "Z", 1], ["success", "Z", "z"], ["idle"]]);
    expect(s.state("A")).toBe("cancelled");
    expect(s.state("B")).toBe("cancelled");
  });

  test("cancelling a running task cascades and then dispatches the next ready task", () => {
    const { s, take } = setup({ concurrency: 1 });
    controlled(s, { id: "A" });
    controlled(s, { id: "B", deps: ["A"] });
    const c = controlled(s, { id: "C" });
    s.start();
    take();
    s.cancel("A");
    expect(take()).toEqual([
      ["cancel", "A", taskError("A", "cancelled", 1, undefined)],
      ["cancel", "B", taskError("B", "dependency", 0, expect.any(TaskError))],
      ["start", "C", 1],
    ]);
    expect(c.calls).toHaveLength(1);
  });
});
