import { describe, expect, test } from "vitest";
import { CycleError, TaskError, type TaskSpec } from "../src/index.js";
import { controlled, instant, scripted, setup, taskError } from "./harness.js";

const noop = () => Promise.resolve(undefined);

describe("add: duplicates and validation", () => {
  test("duplicate id throws a plain Error and leaves the first task intact", async () => {
    const { s, take, flush } = setup();
    const first = instant(s, "A", 1);
    const again = () => s.add({ id: "A", run: () => Promise.resolve(2) });
    expect(again).toThrow(Error);
    expect(again).not.toThrow(RangeError);
    expect(again).not.toThrow(CycleError);
    s.start();
    await flush();
    expect(first.calls).toHaveLength(1);
    expect(take()).toEqual([["start", "A", 1], ["success", "A", 1], ["idle"]]);
  });

  const invalid: Array<[string, Partial<TaskSpec>]> = [
    ["priority NaN", { priority: Number.NaN }],
    ["priority +Infinity", { priority: Number.POSITIVE_INFINITY }],
    ["priority -Infinity", { priority: Number.NEGATIVE_INFINITY }],
    ["retries -1", { retries: -1 }],
    ["retries 0.5", { retries: 0.5 }],
    ["retries NaN", { retries: Number.NaN }],
    ["retries Infinity", { retries: Number.POSITIVE_INFINITY }],
    ["backoffMs -1", { backoffMs: -1 }],
    ["backoffMs NaN", { backoffMs: Number.NaN }],
    ["backoffMs Infinity", { backoffMs: Number.POSITIVE_INFINITY }],
    ["timeoutMs 0", { timeoutMs: 0 }],
    ["timeoutMs -5", { timeoutMs: -5 }],
    ["timeoutMs NaN", { timeoutMs: Number.NaN }],
  ];

  test.each(invalid)("%s throws RangeError and adds nothing", async (_name, opts) => {
    const { s, clock, take, flush } = setup();
    expect(() => s.add({ id: "A", run: noop, ...opts })).toThrow(RangeError);
    expect(() => s.state("A")).toThrow(Error);
    expect(() => s.result("A")).toThrow(Error);
    s.start();
    await flush();
    expect(take()).toEqual([]);
    expect(clock.pendingCount()).toBe(0);
  });

  const valid: Array<[string, Partial<TaskSpec>]> = [
    ["negative priority", { priority: -3 }],
    ["fractional priority", { priority: 0.5 }],
    ["retries 0", { retries: 0 }],
    ["backoffMs 0", { backoffMs: 0 }],
    ["timeoutMs 1", { timeoutMs: 1 }],
    ["timeoutMs undefined", { timeoutMs: undefined }],
    ["timeoutMs Infinity", { timeoutMs: Number.POSITIVE_INFINITY }],
  ];

  test.each(valid)("%s is accepted", (_name, opts) => {
    const { s } = setup();
    s.add({ id: "A", run: noop, ...opts });
    expect(s.state("A")).toBe("queued");
  });

  test("check order: duplicate id wins over invalid options", () => {
    const { s } = setup();
    instant(s, "A");
    expect(() => s.add({ id: "A", run: noop, retries: -1 })).not.toThrow(RangeError);
    expect(() => s.add({ id: "A", run: noop, retries: -1 })).toThrow(Error);
  });

  test("check order: invalid options win over a cycle", () => {
    const { s } = setup();
    expect(() => s.add({ id: "A", run: noop, deps: ["A"], retries: -1 })).toThrow(RangeError);
    expect(() => s.state("A")).toThrow(Error);
  });

  test("check order: duplicate id wins over a cycle", () => {
    const { s } = setup();
    instant(s, "A");
    expect(() => s.add({ id: "A", run: noop, deps: ["A"] })).not.toThrow(CycleError);
    expect(() => s.add({ id: "A", run: noop, deps: ["A"] })).toThrow(Error);
  });
});

describe("add: dependencies", () => {
  test("forward reference waits until the dependency is added and succeeds", async () => {
    const { s, take, flush } = setup();
    const b = instant(s, "B", "b", { deps: ["A"] });
    expect(s.state("B")).toBe("waiting");
    s.start();
    await flush();
    expect(s.state("B")).toBe("waiting");
    expect(take()).toEqual([]);
    instant(s, "A", 42);
    expect(take()).toEqual([["start", "A", 1]]);
    await flush();
    expect(take()).toEqual([
      ["success", "A", 42],
      ["start", "B", 1],
      ["success", "B", "b"],
      ["idle"],
    ]);
    expect(b.calls[0]?.deps).toEqual({ A: 42 });
  });

  test("ctx.deps holds exactly the direct dependencies' values", async () => {
    const { s, flush } = setup({ concurrency: 3 });
    instant(s, "A", 1);
    instant(s, "B", "two");
    const c = instant(s, "C", null, { deps: ["A", "B"] });
    const d = instant(s, "D", null, { deps: ["C"] });
    s.start();
    await flush();
    expect(c.calls[0]?.deps).toEqual({ A: 1, B: "two" });
    expect(d.calls[0]?.deps).toEqual({ C: null });
    expect(Object.keys(d.calls[0]?.deps ?? {})).toEqual(["C"]);
  });

  test("duplicate deps are de-duplicated", async () => {
    const { s, flush } = setup();
    const b = instant(s, "B", "b", { deps: ["A", "A"] });
    instant(s, "A", 1);
    s.start();
    await flush();
    expect(b.calls).toHaveLength(1);
    expect(b.calls[0]?.deps).toEqual({ A: 1 });
    expect(s.state("B")).toBe("succeeded");
  });

  test("a dependency named __proto__ is an own property of ctx.deps", async () => {
    const { s, flush } = setup();
    instant(s, "__proto__", 7);
    const b = instant(s, "B", "b", { deps: ["__proto__"] });
    s.start();
    await flush();
    const deps = b.calls[0]?.deps ?? {};
    expect(Object.hasOwn(deps, "__proto__")).toBe(true);
    expect(deps["__proto__"]).toBe(7);
    expect(Object.keys(deps)).toEqual(["__proto__"]);
    expect(s.state("B")).toBe("succeeded");
  });

  test("a task whose dependency already succeeded is ready immediately", async () => {
    const { s, take, flush } = setup();
    instant(s, "A", 1);
    s.start();
    await flush();
    take();
    const b = instant(s, "B", "b", { deps: ["A"] });
    expect(take()).toEqual([["start", "B", 1]]);
    expect(b.calls[0]?.deps).toEqual({ A: 1 });
  });

  test("a mix of a succeeded and a missing dependency waits for the missing one", async () => {
    const { s, flush } = setup();
    instant(s, "A", 1);
    s.start();
    await flush();
    const c = instant(s, "C", "c", { deps: ["A", "B"] });
    expect(s.state("C")).toBe("waiting");
    instant(s, "B", 2);
    await flush();
    expect(c.calls[0]?.deps).toEqual({ A: 1, B: 2 });
    expect(s.state("C")).toBe("succeeded");
  });
});

describe("add: cycles", () => {
  test("self-dependency throws CycleError with cycle ['a']", () => {
    const { s } = setup();
    let caught: unknown;
    try {
      s.add({ id: "a", run: noop, deps: ["a"] });
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(CycleError);
    expect(caught).toBeInstanceOf(Error);
    const err = caught as CycleError;
    expect(err.cycle).toEqual(["a"]);
    expect(err.name).toBe("CycleError");
    expect(err.message).toBe("dependency cycle: a");
    expect(() => s.state("a")).toThrow(Error);
  });

  test("two-task cycle through a forward reference", () => {
    const { s } = setup();
    s.add({ id: "A", run: noop, deps: ["B"] });
    let caught: unknown;
    try {
      s.add({ id: "B", run: noop, deps: ["A"] });
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(CycleError);
    expect([...(caught as CycleError).cycle].sort()).toEqual(["A", "B"]);
    expect(() => s.state("B")).toThrow(Error);
    expect(s.state("A")).toBe("waiting");
  });

  test("three-task cycle lists each id exactly once and leaves the scheduler unchanged", async () => {
    const { s, take, flush } = setup();
    s.add({ id: "A", run: noop, deps: ["B"] });
    s.add({ id: "B", run: noop, deps: ["C"] });
    let caught: unknown;
    try {
      s.add({ id: "C", run: noop, deps: ["A"] });
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(CycleError);
    const cycle = (caught as CycleError).cycle;
    expect(cycle).toHaveLength(3);
    expect([...cycle].sort()).toEqual(["A", "B", "C"]);
    expect((caught as CycleError).message).toBe(`dependency cycle: ${cycle.join(" -> ")}`);
    expect(() => s.state("C")).toThrow(Error);
    expect(s.state("A")).toBe("waiting");
    expect(s.state("B")).toBe("waiting");
    s.start();
    await flush();
    expect(take()).toEqual([]);
  });

  test("cycle detection is structural: closing a cycle through a cancelled task throws", async () => {
    const { s, take, flush } = setup();
    s.add({ id: "A", run: noop, deps: ["B"] });
    expect(s.cancel("A")).toBe(true);
    expect(take()).toEqual([["cancel", "A", taskError("A", "cancelled", 0, undefined)], ["idle"]]);
    expect(() => s.add({ id: "B", run: noop, deps: ["A"] })).toThrow(CycleError);
    expect(() => s.state("B")).toThrow(Error);
    s.start();
    await flush();
    expect(take()).toEqual([]);
  });

  test("cycle detection walks through cascaded (cancelled) tasks", () => {
    const { s, take } = setup();
    s.add({ id: "A", run: noop, deps: ["B"] });
    s.add({ id: "C", run: noop, deps: ["A"] });
    s.cancel("A");
    take();
    let caught: unknown;
    try {
      s.add({ id: "B", run: noop, deps: ["C"] });
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(CycleError);
    expect([...(caught as CycleError).cycle].sort()).toEqual(["A", "B", "C"]);
    expect(() => s.state("B")).toThrow(Error);
    expect(take()).toEqual([]);
  });

  test("a diamond is not a cycle", async () => {
    const { s, flush } = setup({ concurrency: 4 });
    instant(s, "A", 1);
    instant(s, "B", 2, { deps: ["A"] });
    instant(s, "C", 3, { deps: ["A"] });
    const d = instant(s, "D", 4, { deps: ["B", "C"] });
    s.start();
    await flush();
    expect(d.calls[0]?.deps).toEqual({ B: 2, C: 3 });
    expect(s.state("D")).toBe("succeeded");
  });
});

describe("add: dependency already finished", () => {
  test("dependency already failed: cancelled during add with the dep's TaskError as cause", async () => {
    const { s, take, flush } = setup();
    const boom = new Error("boom");
    scripted(s, { id: "A" }, [{ reject: boom }]);
    s.start();
    await flush();
    const [, failure] = take();
    const aError = failure?.[2];
    expect(aError).toBeInstanceOf(TaskError);
    const c = instant(s, "C", "c", { deps: ["A"] });
    expect(s.state("C")).toBe("cancelled");
    expect(take()).toEqual([["cancel", "C", taskError("C", "dependency", 0, aError)]]);
    await expect(s.result("C")).rejects.toEqual(taskError("C", "dependency", 0, aError));
    await flush();
    expect(c.calls).toHaveLength(0);
    expect(take()).toEqual([]);
  });

  test("dependency already cancelled: cause is that cancel's TaskError", async () => {
    const { s, take } = setup();
    const a = controlled(s, { id: "A" });
    s.start();
    s.cancel("A", "stop");
    const aError = take().find((e) => e[0] === "cancel")?.[2];
    expect(aError).toEqual(taskError("A", "cancelled", 1, "stop"));
    instant(s, "B", "b", { deps: ["A"] });
    expect(take()).toEqual([["cancel", "B", taskError("B", "dependency", 0, aError)]]);
    expect(s.state("B")).toBe("cancelled");
    await expect(s.result("B")).rejects.toMatchObject({ cause: aError });
    expect(a.calls).toHaveLength(1);
  });

  test("with several finished deps the cause is the first failed/cancelled one in deps order", async () => {
    const { s, take, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("a") }]);
    s.add({ id: "B", run: noop, deps: ["Z"] });
    s.cancel("B");
    s.start();
    await flush();
    const errors = new Map(take().filter((e) => e[0] === "failure" || e[0] === "cancel").map((e) => [e[1], e[2]]));
    s.add({ id: "C", run: noop, deps: ["B", "A"] });
    s.add({ id: "D", run: noop, deps: ["A", "B"] });
    expect(take()).toEqual([
      ["cancel", "C", taskError("C", "dependency", 0, errors.get("B"))],
      ["cancel", "D", taskError("D", "dependency", 0, errors.get("A"))],
    ]);
  });

  test("a succeeded dep plus a failed dep still cancels", async () => {
    const { s, take, flush } = setup({ concurrency: 2 });
    instant(s, "OK", 1);
    scripted(s, { id: "BAD" }, [{ reject: new Error("bad") }]);
    s.start();
    await flush();
    take();
    s.add({ id: "C", run: noop, deps: ["OK", "BAD"] });
    expect(s.state("C")).toBe("cancelled");
    expect(take()).toEqual([["cancel", "C", taskError("C", "dependency", 0, expect.any(TaskError))]]);
  });
});
