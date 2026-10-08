import { describe, expect, test } from "vitest";
import { controlled, instant, scripted, setup } from "./harness.js";

describe("synchronous dispatch", () => {
  test("start() invokes run before it returns", () => {
    const { s, take } = setup();
    const a = controlled(s, { id: "A" });
    s.start();
    expect(a.calls).toHaveLength(1);
    expect(s.state("A")).toBe("running");
    expect(take()).toEqual([["start", "A", 1]]);
  });

  test("add() on a started scheduler with a free slot invokes run before it returns", () => {
    const { s, take } = setup();
    s.start();
    const a = controlled(s, { id: "A" });
    expect(a.calls).toHaveLength(1);
    expect(take()).toEqual([["start", "A", 1]]);
  });

  test("cancel() of a running task dispatches the next task before it returns", () => {
    const { s, take } = setup();
    controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    s.start();
    take();
    expect(s.cancel("A")).toBe(true);
    expect(b.calls).toHaveLength(1);
    expect(take()).toEqual([
      ["cancel", "A", expect.objectContaining({ kind: "cancelled" })],
      ["start", "B", 1],
    ]);
  });

  test("a backoff timer callback dispatches synchronously, without a microtask flush", async () => {
    const { s, clock, take, flush } = setup();
    const a = scripted(s, { id: "A", retries: 1, backoffMs: 10 }, [{ reject: new Error("x") }, { ok: 1 }]);
    s.start();
    await flush();
    take();
    expect(clock.fireNextSync()).toBe(true);
    expect(a.calls).toHaveLength(2);
    expect(take()).toEqual([["start", "A", 2]]);
    expect(s.state("A")).toBe("running");
  });

  test("the reaction to a settled task dispatches via microtasks only, never a timer", async () => {
    const { s, clock, take, flush } = setup();
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    s.start();
    take();
    a.resolve(1);
    await flush();
    expect(b.calls).toHaveLength(1);
    expect(clock.setTimeoutCalls).toBe(0);
    expect(take()).toEqual([["success", "A", 1], ["start", "B", 1]]);
  });

  test("the start event precedes the run invocation", () => {
    const { s } = setup();
    const order: string[] = [];
    s.on("start", (id) => {
      order.push(`start:${id}`);
    });
    s.add({
      id: "A",
      run: () => {
        order.push("run:A");
        return Promise.resolve(1);
      },
    });
    s.start();
    expect(order).toEqual(["start:A", "run:A"]);
  });
});

describe("concurrency", () => {
  test("never runs more than `concurrency` tasks at once", async () => {
    const { s, take, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    const c = controlled(s, { id: "C" });
    const d = controlled(s, { id: "D" });
    s.start();
    expect(take()).toEqual([["start", "A", 1], ["start", "B", 1]]);
    expect([s.state("A"), s.state("B"), s.state("C"), s.state("D")]).toEqual([
      "running",
      "running",
      "queued",
      "queued",
    ]);
    expect(c.calls).toHaveLength(0);
    a.resolve("a");
    await flush();
    expect(take()).toEqual([["success", "A", "a"], ["start", "C", 1]]);
    expect(d.calls).toHaveLength(0);
    b.resolve("b");
    c.resolve("c");
    await flush();
    expect(take()).toEqual([["success", "B", "b"], ["start", "D", 1], ["success", "C", "c"]]);
    d.resolve("d");
    await flush();
    expect(take()).toEqual([["success", "D", "d"], ["idle"]]);
  });

  test("a failed attempt waiting out its backoff releases its slot", async () => {
    const { s, clock, take, flush } = setup();
    scripted(s, { id: "A", retries: 1, backoffMs: 50 }, [{ reject: new Error("x") }, { ok: 1 }]);
    const b = controlled(s, { id: "B" });
    s.start();
    await flush();
    expect(b.calls).toHaveLength(1);
    expect(s.state("A")).toBe("retrying");
    expect(take()).toEqual([
      ["start", "A", 1],
      ["retry", "A", 2, 50, expect.any(Error)],
      ["start", "B", 1],
    ]);
    await clock.advance(50);
    expect(s.state("A")).toBe("queued");
    b.resolve(2);
    await flush();
    expect(take()).toEqual([["success", "B", 2], ["start", "A", 2], ["success", "A", 1], ["idle"]]);
  });
});

describe("priority", () => {
  test("higher priority starts first; ties fall back to add order", () => {
    const { s, take } = setup({ concurrency: 1 });
    controlled(s, { id: "A", priority: 0 });
    controlled(s, { id: "B", priority: 5 });
    controlled(s, { id: "C", priority: 5 });
    controlled(s, { id: "D", priority: -1 });
    controlled(s, { id: "E", priority: 0.5 });
    s.start();
    expect(take()).toEqual([["start", "B", 1]]);
    s.cancel("B");
    expect(take()).toEqual([["cancel", "B", expect.anything()], ["start", "C", 1]]);
    s.cancel("C");
    expect(take()).toEqual([["cancel", "C", expect.anything()], ["start", "E", 1]]);
    s.cancel("E");
    expect(take()).toEqual([["cancel", "E", expect.anything()], ["start", "A", 1]]);
    s.cancel("A");
    expect(take()).toEqual([["cancel", "A", expect.anything()], ["start", "D", 1]]);
  });

  test("priority outranks readiness order", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const gate = controlled(s, { id: "G" });
    controlled(s, { id: "LOW", priority: 0 });
    controlled(s, { id: "HIGH", priority: 1, deps: ["G"] });
    s.start();
    take();
    gate.resolve(null);
    await flush();
    expect(take()).toEqual([["success", "G", null], ["start", "HIGH", 1]]);
  });

  test("priority defaults to 0", () => {
    const { s, take } = setup({ concurrency: 1 });
    controlled(s, { id: "NEG", priority: -1 });
    controlled(s, { id: "DEFAULT" });
    s.start();
    expect(take()).toEqual([["start", "DEFAULT", 1]]);
  });
});

describe("ready moment ordering (rule 14)", () => {
  test("tasks made ready by one settle start in add order after earlier-ready tasks", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const x = controlled(s, { id: "X" });
    controlled(s, { id: "Q", deps: ["X"] });
    controlled(s, { id: "P", deps: ["X"] });
    controlled(s, { id: "R" });
    s.start();
    take();
    x.resolve(0);
    await flush();
    expect(take()).toEqual([["success", "X", 0], ["start", "R", 1]]);
    s.cancel("R");
    expect(take()).toEqual([["cancel", "R", expect.anything()], ["start", "Q", 1]]);
    s.cancel("Q");
    expect(take()).toEqual([["cancel", "Q", expect.anything()], ["start", "P", 1]]);
  });

  test("settles in separate microtasks at the same clock time are separate moments", async () => {
    const { s, take, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    controlled(s, { id: "C", deps: ["B"] });
    controlled(s, { id: "D", deps: ["A"] });
    controlled(s, { id: "E" });
    s.start();
    s.pause();
    take();
    b.resolve("b");
    await flush();
    a.resolve("a");
    await flush();
    expect(take()).toEqual([["success", "B", "b"], ["success", "A", "a"]]);
    expect([s.state("C"), s.state("D"), s.state("E")]).toEqual(["queued", "queued", "queued"]);
    s.start();
    expect(take()).toEqual([["start", "E", 1], ["start", "C", 1]]);
    s.cancel("E");
    expect(take()).toEqual([["cancel", "E", expect.anything()], ["start", "D", 1]]);
  });

  test("a re-queued retry (delay 0) enters the ready order at its failure moment", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    scripted(s, { id: "A", retries: 1, backoffMs: 0 }, [{ reject: new Error("x") }, { ok: "a2" }]);
    instant(s, "B", "b");
    s.start();
    await flush();
    expect(take()).toEqual([
      ["start", "A", 1],
      ["retry", "A", 2, 0, expect.any(Error)],
      ["start", "B", 1],
      ["success", "B", "b"],
      ["start", "A", 2],
      ["success", "A", "a2"],
      ["idle"],
    ]);
  });

  test("a task re-queued by a backoff timer goes behind tasks already queued", async () => {
    const { s, clock, take, flush } = setup({ concurrency: 1 });
    scripted(s, { id: "A", retries: 1, backoffMs: 5 }, [{ reject: new Error("x") }, { ok: "a2" }]);
    const b = controlled(s, { id: "B" });
    controlled(s, { id: "C" });
    s.start();
    await flush();
    take();
    await clock.advance(5);
    expect(s.state("A")).toBe("queued");
    b.resolve("b");
    await flush();
    expect(take()).toEqual([["success", "B", "b"], ["start", "C", 1]]);
  });
});

describe("pause and start", () => {
  test("pause() stops new dispatches; running tasks continue", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    s.start();
    take();
    s.pause();
    a.resolve(1);
    await flush();
    expect(take()).toEqual([["success", "A", 1]]);
    expect(s.state("A")).toBe("succeeded");
    expect(s.state("B")).toBe("queued");
    expect(b.calls).toHaveLength(0);
    s.start();
    expect(b.calls).toHaveLength(1);
    expect(take()).toEqual([["start", "B", 1]]);
  });

  test("add() while paused does not dispatch", async () => {
    const { s, take, flush } = setup();
    s.start();
    s.pause();
    const a = controlled(s, { id: "A" });
    await flush();
    expect(a.calls).toHaveLength(0);
    expect(take()).toEqual([]);
    expect(s.state("A")).toBe("queued");
  });

  test("start() and pause() are idempotent", async () => {
    const { s, take, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A" });
    s.start();
    s.start();
    expect(a.calls).toHaveLength(1);
    s.pause();
    s.pause();
    controlled(s, { id: "B" });
    await flush();
    expect(take()).toEqual([["start", "A", 1]]);
    s.start();
    expect(take()).toEqual([["start", "B", 1]]);
  });

  test("a backoff timer that fires while paused leaves the task queued until start()", async () => {
    const { s, clock, take, flush } = setup();
    const a = scripted(s, { id: "A", retries: 1, backoffMs: 20 }, [{ reject: new Error("x") }, { ok: 1 }]);
    s.start();
    await flush();
    s.pause();
    take();
    await clock.advance(20);
    expect(s.state("A")).toBe("queued");
    expect(a.calls).toHaveLength(1);
    expect(clock.pendingCount()).toBe(0);
    expect(take()).toEqual([]);
    s.start();
    expect(a.calls).toHaveLength(2);
    await flush();
    expect(take()).toEqual([["start", "A", 2], ["success", "A", 1], ["idle"]]);
  });

  test("state transitions waiting -> queued -> running -> succeeded", async () => {
    const { s, flush } = setup();
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B", deps: ["A"] });
    expect(s.state("B")).toBe("waiting");
    s.start();
    expect(s.state("A")).toBe("running");
    expect(s.state("B")).toBe("waiting");
    s.pause();
    a.resolve(1);
    await flush();
    expect(s.state("A")).toBe("succeeded");
    expect(s.state("B")).toBe("queued");
    s.start();
    expect(s.state("B")).toBe("running");
    b.resolve(2);
    await flush();
    expect(s.state("B")).toBe("succeeded");
  });
});
