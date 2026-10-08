import { describe, expect, it } from "vitest";
import { Scheduler, TaskError } from "../src/index.js";
import { FakeClock, deferred, flush, never } from "./helpers.js";

function setup(concurrency = 1) {
  const clock = new FakeClock();
  const s = new Scheduler({ concurrency, clock });
  const log: unknown[][] = [];
  s.on("start", (id, attempt) => log.push(["start", id, attempt]));
  s.on("success", (id) => log.push(["success", id]));
  s.on("failure", (id, e) => log.push(["failure", id, e.kind]));
  s.on("cancel", (id, e) => log.push(["cancel", id, e.kind]));
  s.on("idle", () => log.push(["idle"]));
  return { clock, s, log };
}


describe("failure cascades", () => {
  it("cancels transitive dependents in add order, with cause the direct dependency's error", async () => {
    const { s, log } = setup();
    const boom = new Error("boom");
    s.add({ id: "c", deps: ["b"], run: never }); // added before b: forward ref
    s.add({ id: "a", run: async () => { throw boom; } });
    s.add({ id: "b", deps: ["a"], run: never });
    s.add({ id: "d", deps: ["a"], run: never });
    s.add({ id: "other", run: never, priority: -1 });
    let ranB = false;
    s.on("start", (id) => { if (id === "b") ranB = true; });
    s.start();
    await flush();
    expect(ranB).toBe(false);
    expect(log).toEqual([
      ["start", "a", 1],
      ["failure", "a", "failed"],
      ["cancel", "c", "dependency"],
      ["cancel", "b", "dependency"],
      ["cancel", "d", "dependency"],
      ["start", "other", 1],
    ]);
    const a = (await s.result("a").catch((e) => e)) as TaskError;
    const b = (await s.result("b").catch((e) => e)) as TaskError;
    const c = (await s.result("c").catch((e) => e)) as TaskError;
    expect(b).toMatchObject({ kind: "dependency", attempts: 0, cause: a });
    expect(c).toMatchObject({ kind: "dependency", attempts: 0, cause: b });
  });

  it("cancels a task added after its dependency failed, during add, without an idle event", async () => {
    const { s, log } = setup();
    s.add({ id: "a", run: async () => { throw new Error("x"); } });
    s.start();
    await flush();
    log.length = 0;
    s.add({ id: "b", deps: ["a"], run: never });
    expect(s.state("b")).toBe("cancelled");
    expect(log).toEqual([["cancel", "b", "dependency"]]);
    await expect(s.result("b")).rejects.toMatchObject({ kind: "dependency", cause: { kind: "failed" } });
  });
});

describe("cancel()", () => {
  it("returns false for finished and unknown tasks", async () => {
    const { s } = setup();
    s.add({ id: "a", run: async () => 1 });
    s.start();
    await s.result("a");
    expect(s.cancel("a")).toBe(false);
    expect(s.cancel("zzz")).toBe(false);
  });

  it("cancels a running task: aborts, frees the slot immediately, ignores the late result", async () => {
    const { s, log } = setup();
    const a = deferred();
    let signal: AbortSignal | undefined;
    s.add({ id: "a", run: (ctx) => { signal = ctx.signal; return a.promise; } });
    s.add({ id: "dep", deps: ["a"], run: never });
    s.add({ id: "b", run: never });
    s.start();
    const reason = { why: "user" };
    expect(s.cancel("a", reason)).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    expect(s.state("b")).toBe("running");
    expect(signal?.aborted).toBe(true);
    expect(signal?.reason).toMatchObject({ kind: "cancelled", cause: reason, attempts: 1 });
    expect(log).toEqual([
      ["start", "a", 1],
      ["cancel", "a", "cancelled"],
      ["cancel", "dep", "dependency"],
      ["start", "b", 1],
    ]);
    a.resolve(1);
    await flush();
    expect(s.state("a")).toBe("cancelled");
    await expect(s.result("a")).rejects.toMatchObject({ kind: "cancelled", cause: reason, attempts: 1 });
  });

  it("cancels a retrying task and clears its backoff timer", async () => {
    const { clock, s } = setup();
    s.add({ id: "a", retries: 3, backoffMs: 100, run: async () => { throw new Error("x"); } });
    s.start();
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(clock.pending).toBe(1);
    expect(s.cancel("a")).toBe(true);
    expect(clock.pending).toBe(0);
    await expect(s.result("a")).rejects.toMatchObject({ kind: "cancelled", attempts: 1, cause: undefined });
  });

  it("cancels a running task with a timeout and clears the timer", () => {
    const { clock, s } = setup();
    s.add({ id: "a", timeoutMs: 100, run: never });
    s.start();
    expect(clock.pending).toBe(1);
    s.cancel("a");
    expect(clock.pending).toBe(0);
  });

  it("cancels waiting and queued tasks while paused", async () => {
    const { s, log } = setup();
    s.add({ id: "a", run: never });
    s.add({ id: "b", deps: ["x"], run: never });
    expect(s.cancel("a")).toBe(true);
    expect(s.cancel("b")).toBe(true);
    expect(log).toEqual([["cancel", "a", "cancelled"], ["cancel", "b", "cancelled"], ["idle"]]);
  });
});

describe("idle", () => {
  it("emits idle once after the last task finishes, after start events", async () => {
    const { s, log } = setup();
    s.add({ id: "a", run: async () => 1 });
    s.add({ id: "b", run: async () => 2 });
    s.start();
    await s.onIdle();
    expect(log).toEqual([["start", "a", 1], ["success", "a"], ["start", "b", 1], ["success", "b"], ["idle"]]);
  });

  it("resolves onIdle called from the last task's success listener once idle is announced", async () => {
    const { s, log } = setup();
    let resolved: Promise<void> | undefined;
    s.on("success", () => { resolved = s.onIdle().then(() => { log.push(["onIdle resolved"]); }); });
    s.add({ id: "a", run: async () => 1 });
    s.start();
    await flush();
    await resolved;
    expect(log.slice(-2)).toEqual([["idle"], ["onIdle resolved"]]);
  });

  it("does not emit idle for an empty scheduler and resolves onIdle immediately", async () => {
    const { s, log } = setup();
    s.start();
    await s.onIdle();
    expect(log).toEqual([]);
  });

  it("is not idle while a task waits on a dependency that was never added", async () => {
    const { s } = setup();
    s.add({ id: "a", deps: ["ghost"], run: async () => 1 });
    s.start();
    let idle = false;
    void s.onIdle().then(() => { idle = true; });
    await flush();
    expect(idle).toBe(false);
    s.add({ id: "ghost", run: async () => 0 });
    await flush();
    expect(idle).toBe(true);
  });
});

describe("events", () => {
  it("unsubscribes listeners and isolates throwing listeners", async () => {
    const { s } = setup();
    const seen: string[] = [];
    s.on("start", () => { throw new Error("listener bug"); });
    const off = s.on("start", (id) => seen.push(id));
    s.add({ id: "a", run: async () => 1 });
    s.start();
    off();
    s.add({ id: "b", run: async () => 1 });
    await s.onIdle();
    expect(seen).toEqual(["a"]);
    expect(s.state("b")).toBe("succeeded");
  });

  it("lets a listener pause dispatching mid-pass", () => {
    const s = new Scheduler({ concurrency: 3, clock: new FakeClock() });
    const started: string[] = [];
    s.on("start", (id) => { started.push(id); s.pause(); });
    for (const id of ["a", "b", "c"]) s.add({ id, run: never });
    s.start();
    expect(started).toEqual(["a"]);
    expect(s.state("a")).toBe("running");
    expect(s.state("b")).toBe("queued");
  });

  it("starts tasks added re-entrantly from a listener before the outer call returns", async () => {
    const s = new Scheduler({ concurrency: 2, clock: new FakeClock() });
    const order: string[] = [];
    s.on("start", (id) => {
      order.push(id);
      if (id === "a") s.add({ id: "b", run: never });
    });
    s.add({ id: "a", run: never });
    s.start();
    expect(order).toEqual(["a", "b"]);
  });
});

describe("validation", () => {
  it("rejects bad task specs without adding them", () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    const run = async () => 1;
    expect(() => s.add({ id: "a", run: undefined as never })).toThrow(TypeError);
    expect(() => s.add({ id: "a", run, priority: NaN })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, priority: Infinity })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, retries: -1 })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, retries: 1.5 })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, backoffMs: -1 })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, timeoutMs: 0 })).toThrow(RangeError);
    expect(() => s.state("a")).toThrow();
    s.add({ id: "a", run, priority: -2.5 });
  });
});
