import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { CycleError, TaskError } from "../src/index.js";
import { controlled, instant, macrotask, scripted, setup, taskError, trapUnhandled } from "./harness.js";

describe("result()", () => {
  test("resolves with the task's value, whether called before or after success", async () => {
    const { s, flush } = setup();
    const a = controlled<{ n: number }>(s, { id: "A" });
    const before = s.result<{ n: number }>("A");
    s.start();
    const value = { n: 1 };
    a.resolve(value);
    await flush();
    await expect(before).resolves.toBe(value);
    await expect(s.result("A")).resolves.toBe(value);
  });

  test("rejects with a TaskError exposing taskId, kind, attempts and cause", async () => {
    const { s, flush } = setup();
    const cause = new Error("nope");
    scripted(s, { id: "A", retries: 1 }, [{ reject: new Error("first") }, { reject: cause }]);
    s.start();
    await flush();
    const err = await s.result("A").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(TaskError);
    expect(err).toBeInstanceOf(Error);
    const te = err as TaskError;
    expect(te.name).toBe("TaskError");
    expect(te.taskId).toBe("A");
    expect(te.kind).toBe("failed");
    expect(te.attempts).toBe(2);
    expect(te.cause).toBe(cause);
    expect(te.message).toBe("task A failed");
  });

  test("the rejection is the same object the failure event carried", async () => {
    const { s, take, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("x") }]);
    s.start();
    await flush();
    const failure = take().find((e) => e[0] === "failure");
    await expect(s.result("A")).rejects.toBe(failure?.[2]);
  });

  test("the rejection for a cancelled task is the cancel event's TaskError", async () => {
    const { s, take } = setup();
    instant(s, "A");
    s.cancel("A", 42);
    const cancel = take().find((e) => e[0] === "cancel");
    await expect(s.result("A")).rejects.toBe(cancel?.[2]);
    expect(cancel?.[2]).toEqual(taskError("A", "cancelled", 0, 42));
  });

  test("unknown id throws synchronously", () => {
    const { s } = setup();
    expect(() => s.result("missing")).toThrow(Error);
  });

  test("repeated calls settle the same way", async () => {
    const { s, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("x") }]);
    const p1 = s.result("A").catch((e: unknown) => e);
    s.start();
    await flush();
    const p2 = s.result("A").catch((e: unknown) => e);
    const [e1, e2] = await Promise.all([p1, p2]);
    expect(e1).toBeInstanceOf(TaskError);
    expect(e2).toBe(e1);
  });

  test("result for a dependency-cancelled task rejects with kind dependency and attempts 0", async () => {
    const { s, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("x") }]);
    controlled(s, { id: "B", deps: ["A"] });
    const pending = s.result("B");
    s.start();
    await flush();
    await expect(pending).rejects.toEqual(taskError("B", "dependency", 0, expect.any(TaskError)));
  });
});

describe("error classes", () => {
  test("TaskError defaults its message and keeps the fields", () => {
    const cause = new Error("c");
    const err = new TaskError("t1", "timeout", 3, cause);
    expect(err.message).toBe("task t1 timeout");
    expect(err.name).toBe("TaskError");
    expect(err.taskId).toBe("t1");
    expect(err.kind).toBe("timeout");
    expect(err.attempts).toBe(3);
    expect(err.cause).toBe(cause);
    expect(err).toBeInstanceOf(Error);
    expect(new TaskError("t1", "failed", 1, undefined, "custom").message).toBe("custom");
  });

  test("CycleError joins the cycle into its message", () => {
    const err = new CycleError(["a", "b"]);
    expect(err.message).toBe("dependency cycle: a -> b");
    expect(err.name).toBe("CycleError");
    expect(err.cycle).toEqual(["a", "b"]);
    expect(err).toBeInstanceOf(Error);
  });
});

describe("no unhandled rejections", () => {
  let trap: ReturnType<typeof trapUnhandled>;
  beforeEach(() => {
    trap = trapUnhandled();
  });
  afterEach(() => {
    trap.stop();
  });

  test("a failing task nobody asked the result of", async () => {
    const { s, flush } = setup();
    scripted(s, { id: "A", retries: 1 }, [{ reject: new Error("x") }, { reject: new Error("y") }]);
    s.start();
    await flush();
    await macrotask();
    expect(s.state("A")).toBe("failed");
    expect(trap.seen).toEqual([]);
  });

  test("a synchronously throwing task nobody asked the result of", async () => {
    const { s, flush } = setup();
    scripted(s, { id: "A" }, [{ throw: new Error("sync") }]);
    s.start();
    await flush();
    await macrotask();
    expect(s.state("A")).toBe("failed");
    expect(trap.seen).toEqual([]);
  });

  test("cancelled and cascaded tasks nobody asked the result of", async () => {
    const { s, flush } = setup();
    controlled(s, { id: "A" });
    controlled(s, { id: "B", deps: ["A"] });
    s.start();
    s.cancel("A");
    await flush();
    await macrotask();
    expect(trap.seen).toEqual([]);
  });

  test("a task cancelled during add because its dependency failed", async () => {
    const { s, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("x") }]);
    s.start();
    await flush();
    controlled(s, { id: "B", deps: ["A"] });
    await macrotask();
    expect(trap.seen).toEqual([]);
  });

  test("late rejections from timed-out and cancelled attempts", async () => {
    const { s, clock, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A", timeoutMs: 10 });
    const b = controlled(s, { id: "B" });
    s.start();
    await clock.advance(10);
    s.cancel("B");
    a.reject(new Error("late a"));
    b.reject(new Error("late b"));
    await flush();
    await macrotask();
    expect(trap.seen).toEqual([]);
  });

  test("a task that times out on every attempt", async () => {
    const { s, clock } = setup();
    controlled(s, { id: "A", timeoutMs: 5, retries: 2, backoffMs: 1 });
    s.start();
    await clock.advance(100);
    await macrotask();
    expect(s.state("A")).toBe("failed");
    expect(trap.seen).toEqual([]);
  });

  test("result() called and caught sees the TaskError, still no unhandled rejection", async () => {
    const { s, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("x") }]);
    s.start();
    await flush();
    await expect(s.result("A")).rejects.toBeInstanceOf(TaskError);
    await macrotask();
    expect(trap.seen).toEqual([]);
  });
});
