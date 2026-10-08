import { describe, expect, test } from "vitest";
import { TaskError } from "../src/index.js";
import { controlled, instant, scripted, setup, taskError } from "./harness.js";

describe("event sequences", () => {
  test("diamond: success, then starts of unblocked dependents, then idle at the end", async () => {
    const { s, take, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B", deps: ["A"] });
    const c = controlled(s, { id: "C", deps: ["A"] });
    const d = controlled(s, { id: "D", deps: ["B", "C"] });
    s.start();
    expect(take()).toEqual([["start", "A", 1]]);
    a.resolve("a");
    await flush();
    expect(take()).toEqual([["success", "A", "a"], ["start", "B", 1], ["start", "C", 1]]);
    b.resolve("b");
    await flush();
    expect(take()).toEqual([["success", "B", "b"]]);
    c.resolve("c");
    await flush();
    expect(take()).toEqual([["success", "C", "c"], ["start", "D", 1]]);
    expect(d.ctx().deps).toEqual({ B: "b", C: "c" });
    d.resolve("d");
    await flush();
    expect(take()).toEqual([["success", "D", "d"], ["idle"]]);
  });

  test("failure: own event, cascade, next start; idle only once everything is finished", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    controlled(s, { id: "B", deps: ["A"] });
    const c = controlled(s, { id: "C" });
    s.start();
    expect(take()).toEqual([["start", "A", 1]]);
    const boom = new Error("boom");
    a.reject(boom);
    await flush();
    expect(take()).toEqual([
      ["failure", "A", taskError("A", "failed", 1, boom)],
      ["cancel", "B", taskError("B", "dependency", 0, expect.any(TaskError))],
      ["start", "C", 1],
    ]);
    c.resolve("c");
    await flush();
    expect(take()).toEqual([["success", "C", "c"], ["idle"]]);
  });

  test("failure with nothing left: own event, cascades in add order, idle", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    controlled(s, { id: "C", deps: ["A"] });
    controlled(s, { id: "B", deps: ["C"] });
    s.start();
    take();
    a.reject(new Error("x"));
    await flush();
    expect(take().map((e) => e.slice(0, 2))).toEqual([
      ["failure", "A"],
      ["cancel", "C"],
      ["cancel", "B"],
      ["idle"],
    ]);
  });

  test("success listener receives the exact value object", async () => {
    const { s, flush } = setup();
    const value = { big: [1, 2, 3] };
    const seen: unknown[] = [];
    s.on("success", (_id, v) => {
      seen.push(v);
    });
    instant(s, "A", value);
    s.start();
    await flush();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toBe(value);
  });

  test("retry listener receives (id, nextAttempt, delayMs, error)", async () => {
    const { s, flush } = setup();
    const err = new Error("e");
    const seen: unknown[][] = [];
    s.on("retry", (...args) => {
      seen.push(args);
    });
    scripted(s, { id: "A", retries: 1, backoffMs: 7 }, [{ reject: err }, { ok: 1 }]);
    s.start();
    await flush();
    expect(seen).toEqual([["A", 2, 7, err]]);
  });
});

describe("subscriptions", () => {
  test("unsubscribe stops delivery; calling it twice is harmless; others keep receiving", async () => {
    const { s, take, flush } = setup();
    const mine: string[] = [];
    const off = s.on("start", (id) => {
      mine.push(id);
    });
    instant(s, "A");
    instant(s, "B");
    s.start();
    await flush();
    expect(mine).toEqual(["A", "B"]);
    off();
    expect(() => off()).not.toThrow();
    instant(s, "C");
    await flush();
    expect(mine).toEqual(["A", "B"]);
    expect(take().filter((e) => e[0] === "start").map((e) => e[1])).toEqual(["A", "B", "C"]);
  });

  test("every listener of an event is called, and a throwing one is swallowed", async () => {
    const { s, take, flush } = setup();
    const calls: string[] = [];
    s.on("start", () => {
      calls.push("first");
      throw new Error("listener boom");
    });
    s.on("start", () => {
      calls.push("second");
    });
    const a = instant(s, "A", 1);
    expect(() => s.start()).not.toThrow();
    expect(calls).toEqual(["first", "second"]);
    expect(a.calls).toHaveLength(1);
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["success", "A", 1], ["idle"]]);
  });

  test("a throwing success listener does not stop the next dispatch", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    s.on("success", () => {
      throw new Error("boom");
    });
    const a = controlled(s, { id: "A" });
    controlled(s, { id: "B" });
    s.start();
    take();
    a.resolve(1);
    await flush();
    expect(take()).toEqual([["success", "A", 1], ["start", "B", 1]]);
    expect(s.state("B")).toBe("running");
  });

  test("a throwing idle listener leaves the scheduler usable", async () => {
    const { s, take, flush } = setup();
    s.on("idle", () => {
      throw new Error("idle boom");
    });
    instant(s, "A");
    s.start();
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["success", "A", "A"], ["idle"]]);
    instant(s, "B");
    await flush();
    expect(take()).toEqual([["start", "B", 1], ["success", "B", "B"], ["idle"]]);
  });

  test("a listener may unsubscribe itself during emission", async () => {
    const { s, flush } = setup();
    const mine: string[] = [];
    const off = s.on("start", (id) => {
      mine.push(id);
      off();
    });
    instant(s, "A");
    instant(s, "B");
    expect(() => s.start()).not.toThrow();
    await flush();
    expect(mine).toEqual(["A"]);
  });
});

describe("re-entrancy (rule 13)", () => {
  test("add() inside a failure listener: cascade finishes before the new task starts", async () => {
    const { s, take, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A" });
    controlled(s, { id: "B", deps: ["A"] });
    let nested: unknown;
    s.on("failure", () => {
      instant(s, "N", "n");
      nested = s.state("N");
    });
    s.start();
    take();
    a.reject(new Error("x"));
    await flush();
    expect(nested).toBe("queued");
    expect(take()).toEqual([
      ["failure", "A", taskError("A", "failed", 1, expect.any(Error))],
      ["cancel", "B", taskError("B", "dependency", 0, expect.any(TaskError))],
      ["start", "N", 1],
      ["success", "N", "n"],
      ["idle"],
    ]);
  });

  test("cancel() inside a success listener takes effect before the next dispatch", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    const c = controlled(s, { id: "C" });
    let returned: boolean | undefined;
    s.on("success", (id) => {
      if (id === "A") returned = s.cancel("B", "from-listener");
    });
    s.start();
    take();
    a.resolve(1);
    await flush();
    expect(returned).toBe(true);
    expect(take()).toEqual([
      ["success", "A", 1],
      ["cancel", "B", taskError("B", "cancelled", 0, "from-listener")],
      ["start", "C", 1],
    ]);
    expect(b.calls).toHaveLength(0);
    expect(c.calls).toHaveLength(1);
  });

  test("add() inside an idle listener dispatches before the outer call returns and idles again later", async () => {
    const { s, take, flush } = setup();
    const a = controlled(s, { id: "A" });
    let added = false;
    s.on("idle", () => {
      if (added) return;
      added = true;
      instant(s, "N", "n");
    });
    s.start();
    take();
    a.resolve(1);
    await flush();
    expect(take()).toEqual([
      ["success", "A", 1],
      ["idle"],
      ["start", "N", 1],
      ["success", "N", "n"],
      ["idle"],
    ]);
  });

  test("pause() inside a success listener stops the next dispatch", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    s.on("success", () => {
      s.pause();
    });
    s.start();
    take();
    a.resolve(1);
    await flush();
    expect(take()).toEqual([["success", "A", 1]]);
    expect(b.calls).toHaveLength(0);
    expect(s.state("B")).toBe("queued");
    s.start();
    expect(take()).toEqual([["start", "B", 1]]);
  });
});

describe("cancel from a start listener (rule 12)", () => {
  test("run is not invoked, the task ends cancelled and the slot goes to the next task", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    let returned: boolean | undefined;
    s.on("start", (id) => {
      if (id === "A") returned = s.cancel("A", "veto");
    });
    s.start();
    expect(returned).toBe(true);
    expect(a.calls).toHaveLength(0);
    expect(b.calls).toHaveLength(1);
    expect(s.state("A")).toBe("cancelled");
    expect(take()).toEqual([
      ["start", "A", 1],
      ["cancel", "A", taskError("A", "cancelled", 1, "veto")],
      ["start", "B", 1],
    ]);
    await expect(s.result("A")).rejects.toMatchObject({ kind: "cancelled", cause: "veto" });
    b.resolve(2);
    await flush();
    expect(take()).toEqual([["success", "B", 2], ["idle"]]);
  });

  test("cancelling the started task cascades to its dependents", () => {
    const { s, take } = setup({ concurrency: 1 });
    controlled(s, { id: "A" });
    controlled(s, { id: "B", deps: ["A"] });
    s.on("start", (id) => {
      if (id === "A") s.cancel("A");
    });
    s.start();
    expect(take().map((e) => e.slice(0, 2))).toEqual([
      ["start", "A"],
      ["cancel", "A"],
      ["cancel", "B"],
      ["idle"],
    ]);
  });
});
