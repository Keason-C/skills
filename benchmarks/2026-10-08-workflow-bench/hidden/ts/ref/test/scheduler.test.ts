import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CycleError, Scheduler, TaskError, type TaskContext } from "../src/index.js";
import { FakeClock, deferred, flush } from "./fake-clock.js";

let clock: FakeClock;
const unhandled: unknown[] = [];
const onUnhandled = (e: unknown) => unhandled.push(e);

beforeEach(() => {
  clock = new FakeClock();
  unhandled.length = 0;
  process.on("unhandledRejection", onUnhandled);
});
afterEach(async () => {
  await flush();
  await flush();
  process.off("unhandledRejection", onUnhandled);
  expect(unhandled).toEqual([]);
});

function make(concurrency = 1) {
  return new Scheduler({ concurrency, clock });
}

/** Records every event as a compact string. */
function record(s: Scheduler): string[] {
  const log: string[] = [];
  s.on("start", (id, a) => log.push(`start:${id}:${a}`));
  s.on("success", (id, v) => log.push(`success:${id}:${String(v)}`));
  s.on("retry", (id, n, d) => log.push(`retry:${id}:${n}:${d}`));
  s.on("failure", (id, e) => log.push(`failure:${id}:${e.kind}`));
  s.on("cancel", (id, e) => log.push(`cancel:${id}:${e.kind}`));
  s.on("idle", () => log.push("idle"));
  return log;
}

/** A task body controlled by the test: resolve/reject each attempt by hand. */
function controlled() {
  const attempts: Array<ReturnType<typeof deferred> & { ctx: TaskContext }> = [];
  const run = (ctx: TaskContext) => {
    const d = deferred();
    attempts.push({ ...d, ctx });
    return d.promise;
  };
  return { run, attempts };
}

const ok = (v: unknown) => () => Promise.resolve(v);

async function rejection(p: Promise<unknown>): Promise<TaskError> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(TaskError);
    return e as TaskError;
  }
  throw new Error("expected rejection");
}

describe("construction and validation", () => {
  it("rejects invalid concurrency", () => {
    for (const c of [0, -1, 1.5, NaN, Infinity]) {
      expect(() => new Scheduler({ concurrency: c, clock })).toThrow(RangeError);
    }
    expect(() => new Scheduler({ concurrency: 3, clock })).not.toThrow();
  });

  it("validates task options with RangeError", () => {
    const s = make();
    const run = ok(1);
    expect(() => s.add({ id: "a", run, priority: NaN })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, priority: Infinity })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, retries: -1 })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, retries: 1.5 })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, backoffMs: -1 })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, timeoutMs: 0 })).toThrow(RangeError);
    expect(() => s.add({ id: "a", run, timeoutMs: -5 })).toThrow(RangeError);
    // nothing was added
    expect(() => s.state("a")).toThrow(Error);
    s.add({ id: "a", run, priority: -2.5 });
    expect(s.state("a")).toBe("queued");
  });

  it("throws on duplicate ids and unknown ids", () => {
    const s = make();
    s.add({ id: "a", run: ok(1) });
    expect(() => s.add({ id: "a", run: ok(2) })).toThrow(Error);
    expect(() => s.state("nope")).toThrow(Error);
    expect(() => s.result("nope")).toThrow(Error);
    expect(s.cancel("nope")).toBe(false);
  });
});

describe("dispatch", () => {
  it("is paused until start() and dispatches synchronously", async () => {
    const s = make(2);
    const log = record(s);
    const a = controlled();
    s.add({ id: "a", run: a.run });
    expect(s.state("a")).toBe("queued");
    expect(a.attempts).toHaveLength(0);
    s.start();
    expect(a.attempts).toHaveLength(1);
    expect(s.state("a")).toBe("running");
    const b = controlled();
    s.add({ id: "b", run: b.run });
    expect(b.attempts).toHaveLength(1); // run invoked before add returned
    a.attempts[0]!.resolve("A");
    b.attempts[0]!.resolve("B");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(await s.result("a")).toBe("A");
    expect(log).toEqual(["start:a:1", "start:b:1", "success:a:A", "success:b:B", "idle"]);
  });

  it("respects concurrency and refills in the settle reaction", async () => {
    const s = make(2);
    const tasks = ["a", "b", "c", "d"].map((id) => ({ id, c: controlled() }));
    for (const t of tasks) s.add({ id: t.id, run: t.c.run });
    s.start();
    expect(tasks.map((t) => s.state(t.id))).toEqual(["running", "running", "queued", "queued"]);
    tasks[1]!.c.attempts[0]!.resolve(1);
    await flush();
    expect(tasks.map((t) => s.state(t.id))).toEqual(["running", "succeeded", "running", "queued"]);
    for (const t of tasks) t.c.attempts[0]?.resolve(1);
    await flush();
    tasks[3]!.c.attempts[0]!.resolve(1);
    await s.onIdle();
    expect(tasks.every((t) => s.state(t.id) === "succeeded")).toBe(true);
  });

  it("pause stops new starts; start resumes; idempotent", async () => {
    const s = make(1);
    const a = controlled();
    const b = controlled();
    s.add({ id: "a", run: a.run });
    s.add({ id: "b", run: b.run });
    s.start();
    s.start();
    s.pause();
    s.pause();
    a.attempts[0]!.resolve(1);
    await flush();
    expect(s.state("b")).toBe("queued");
    s.start();
    expect(s.state("b")).toBe("running");
    b.attempts[0]!.resolve(2);
    await s.onIdle();
  });

  it("orders by priority, then ready order, then add order", async () => {
    const s = make(1);
    const order: string[] = [];
    const gate = controlled();
    const trackOk = (id: string) => () => {
      order.push(id);
      return Promise.resolve(id);
    };
    s.add({ id: "gate", run: gate.run, priority: 100 });
    s.add({ id: "low", run: trackOk("low"), priority: -1.5 });
    s.add({ id: "x", run: trackOk("x") });
    s.add({ id: "y", run: trackOk("y") });
    s.add({ id: "high", run: trackOk("high"), priority: 0.5 });
    s.start();
    gate.attempts[0]!.resolve(0);
    await s.onIdle();
    expect(order).toEqual(["high", "x", "y", "low"]);
  });

  it("equal priority: earlier-ready first, simultaneous-ready in add order", async () => {
    const s = make(1);
    const order: string[] = [];
    const track = (id: string) => () => {
      order.push(id);
      return Promise.resolve(id);
    };
    const d1 = controlled();
    const d2 = controlled();
    const blocker = controlled();
    s.add({ id: "d1", run: d1.run, priority: 10 });
    s.add({ id: "d2", run: d2.run, priority: 10 });
    s.add({ id: "blocker", run: blocker.run, priority: 5 });
    s.add({ id: "x", run: track("x"), deps: ["d1"] }); // added first, ready later
    s.add({ id: "p", run: track("p"), deps: ["d2"] });
    s.add({ id: "q", run: track("q"), deps: ["d2"] });
    s.start(); // runs d1
    // run d2 before d1 finishes: concurrency 1, so finish d1 last via ordering: d1 is running.
    expect(s.state("d1")).toBe("running");
    d1.attempts[0]!.resolve(1); // x becomes ready; d2 starts
    await flush();
    expect(s.state("x")).toBe("queued");
    expect(s.state("d2")).toBe("running");
    d2.attempts[0]!.resolve(2); // p, q ready together after x; blocker (prio 5) goes first
    await flush();
    expect(s.state("blocker")).toBe("running");
    blocker.attempts[0]!.resolve(3);
    await s.onIdle();
    expect(order).toEqual(["x", "p", "q"]);
  });

  it("ready order beats add order when tasks become ready at different moments", async () => {
    const s = make(1);
    const order: string[] = [];
    const track = (id: string) => () => {
      order.push(id);
      return Promise.resolve(id);
    };
    const hold = controlled();
    const dep = controlled();
    s.add({ id: "hold", run: hold.run, priority: 1 });
    s.add({ id: "dep", run: dep.run, priority: 1 });
    s.add({ id: "early-added", run: track("early-added"), deps: ["dep"] });
    s.start();
    s.add({ id: "late-added", run: track("late-added") }); // ready now
    hold.attempts[0]!.resolve(0);
    await flush();
    dep.attempts[0]!.resolve(0); // early-added becomes ready after late-added
    await s.onIdle();
    expect(order).toEqual(["late-added", "early-added"]);
  });

  it("treats a synchronous throw like a rejection", async () => {
    const s = make(1);
    s.add({
      id: "a",
      run: () => {
        throw new Error("boom");
      },
    });
    s.start();
    expect(s.state("a")).toBe("running");
    const e = await rejection(s.result("a"));
    expect(e.kind).toBe("failed");
    expect((e.cause as Error).message).toBe("boom");
    expect(e.attempts).toBe(1);
  });
});

describe("dependencies", () => {
  it("passes dependency results in ctx.deps and supports forward references", async () => {
    const s = make(2);
    let seen: Record<string, unknown> | undefined;
    s.add({
      id: "c",
      deps: ["a", "b"],
      run: async (ctx) => {
        seen = ctx.deps;
        return 3;
      },
    });
    s.start();
    expect(s.state("c")).toBe("waiting");
    s.add({ id: "a", run: ok(1) });
    await flush();
    expect(s.state("c")).toBe("waiting");
    s.add({ id: "b", run: ok(2) });
    expect(await s.result("c")).toBe(3);
    expect(seen).toEqual({ a: 1, b: 2 });
  });

  it("missing deps keep the scheduler busy; cancelling them works", async () => {
    const s = make(1);
    const log = record(s);
    s.add({ id: "w", deps: ["ghost"], run: ok(1) });
    s.start();
    let idle = false;
    void s.onIdle().then(() => (idle = true));
    await flush();
    expect(idle).toBe(false);
    expect(s.cancel("w", "nope")).toBe(true);
    await flush();
    expect(idle).toBe(true);
    const e = await rejection(s.result("w"));
    expect(e.kind).toBe("cancelled");
    expect(e.cause).toBe("nope");
    expect(e.attempts).toBe(0);
    expect(log).toEqual(["cancel:w:cancelled", "idle"]);
  });

  it("detects cycles at add and leaves the scheduler unchanged", () => {
    const s = make(1);
    const self = (() => {
      try {
        s.add({ id: "s", deps: ["s"], run: ok(1) });
      } catch (e) {
        return e;
      }
    })();
    expect(self).toBeInstanceOf(CycleError);
    expect(self).toBeInstanceOf(Error);
    expect((self as CycleError).name).toBe("CycleError");
    expect((self as CycleError).cycle).toEqual(["s"]);
    expect(() => s.state("s")).toThrow();

    s.add({ id: "a", deps: ["b"], run: ok(1) });
    s.add({ id: "b", deps: ["c"], run: ok(1) });
    s.add({ id: "z", deps: ["a"], run: ok(1) }); // not on the cycle
    let err: unknown;
    try {
      s.add({ id: "c", deps: ["x", "a"], run: ok(1) });
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(CycleError);
    expect([...(err as CycleError).cycle].sort()).toEqual(["a", "b", "c"]);
    expect(() => s.state("c")).toThrow();
    // the id is still free
    s.add({ id: "c", run: ok(1) });
    expect(s.state("c")).toBe("queued");
  });

  it("cancels a task immediately when added after its dependency failed", async () => {
    const s = make(1);
    s.add({ id: "a", run: () => Promise.reject(new Error("x")) });
    s.start();
    await flush();
    expect(s.state("a")).toBe("failed");
    const log = record(s);
    s.add({ id: "b", deps: ["a"], run: ok(1) });
    expect(s.state("b")).toBe("cancelled");
    expect(log).toEqual(["cancel:b:dependency"]); // no idle: it never became busy
    const eb = await rejection(s.result("b"));
    expect(eb.kind).toBe("dependency");
    expect(eb.attempts).toBe(0);
    expect(eb.cause).toBe(await rejection(s.result("a")));
  });

  it("cascades failure in add order with direct-dependency causes, then starts, then idle", async () => {
    const s = make(1);
    const a = controlled();
    s.add({ id: "a", run: a.run });
    s.add({ id: "b", deps: ["a"], run: ok("b") });
    s.add({ id: "other", run: ok("o") });
    s.add({ id: "c", deps: ["b"], run: ok("c") });
    s.add({ id: "d", deps: ["a", "c"], run: ok("d") });
    s.start();
    const log = record(s);
    a.attempts[0]!.reject(new Error("bad"));
    await s.onIdle();
    expect(log).toEqual([
      "failure:a:failed",
      "cancel:b:dependency",
      "cancel:c:dependency",
      "cancel:d:dependency",
      "start:other:1",
      "success:other:o",
      "idle",
    ]);
    const ea = await rejection(s.result("a"));
    const eb = await rejection(s.result("b"));
    const ec = await rejection(s.result("c"));
    expect(ea.kind).toBe("failed");
    expect((ea.cause as Error).message).toBe("bad");
    expect(eb.cause).toBe(ea);
    expect(ec.cause).toBe(eb);
    expect(ec.attempts).toBe(0);
  });
});

describe("retries and backoff", () => {
  it("waits backoffMs * 2^(n-1) on the clock between attempts", async () => {
    const s = make(1);
    const log = record(s);
    const t = controlled();
    s.add({ id: "t", run: t.run, retries: 3, backoffMs: 100 });
    s.start();
    t.attempts[0]!.reject(new Error("e1"));
    await flush();
    expect(s.state("t")).toBe("retrying");
    expect(clock.pending).toBe(1);
    await clock.advance(99);
    expect(t.attempts).toHaveLength(1);
    await clock.advance(1);
    expect(t.attempts).toHaveLength(2);
    expect(t.attempts[1]!.ctx.attempt).toBe(2);
    t.attempts[1]!.reject(new Error("e2"));
    await flush();
    await clock.advance(199);
    expect(t.attempts).toHaveLength(2);
    await clock.advance(1);
    t.attempts[2]!.reject(new Error("e3"));
    await flush();
    await clock.advance(400);
    expect(t.attempts).toHaveLength(4);
    t.attempts[3]!.reject(new Error("e4"));
    const e = await rejection(s.result("t"));
    expect(e.kind).toBe("failed");
    expect(e.attempts).toBe(4);
    expect((e.cause as Error).message).toBe("e4");
    expect(log).toEqual([
      "start:t:1",
      "retry:t:2:100",
      "start:t:2",
      "retry:t:3:200",
      "start:t:3",
      "retry:t:4:400",
      "start:t:4",
      "failure:t:failed",
      "idle",
    ]);
    expect(clock.pending).toBe(0);
  });

  it("retry event carries the attempt error; success after retry", async () => {
    const s = make(1);
    const errors: unknown[] = [];
    s.on("retry", (_id, _n, _d, e) => errors.push(e));
    let n = 0;
    const boom = new Error("first");
    s.add({ id: "t", retries: 1, backoffMs: 10, run: async () => (++n === 1 ? Promise.reject(boom) : "ok") });
    s.start();
    await flush();
    await clock.advance(10);
    expect(await s.result("t")).toBe("ok");
    expect(errors).toEqual([boom]);
  });

  it("backoff 0 requeues synchronously without creating a timer", async () => {
    const s = make(1);
    const log = record(s);
    const t = controlled();
    const other = controlled();
    s.add({ id: "t", run: t.run, retries: 1, priority: 0 });
    s.add({ id: "other", run: other.run, priority: 0 });
    s.start();
    let stateInRetry: string | undefined;
    s.on("retry", () => (stateInRetry = s.state("t")));
    t.attempts[0]!.reject(new Error("x"));
    await flush();
    expect(clock.pending).toBe(0);
    expect(stateInRetry).toBe("retrying");
    // t re-entered the ready order after "other" (which became ready at add time)
    expect(s.state("other")).toBe("running");
    expect(s.state("t")).toBe("queued");
    other.attempts[0]!.resolve(1);
    await flush();
    t.attempts[1]!.resolve(2);
    await s.onIdle();
    expect(log).toEqual([
      "start:t:1",
      "retry:t:2:0",
      "start:other:1",
      "success:other:1",
      "start:t:2",
      "success:t:2",
      "idle",
    ]);
  });

  it("a retrying task re-enters the ready order when its backoff ends", async () => {
    const s = make(1);
    const order: string[] = [];
    let n = 0;
    const hold = controlled();
    s.add({
      id: "r",
      retries: 1,
      backoffMs: 5,
      run: () => {
        order.push(`r${++n}`);
        return n === 1 ? Promise.reject(new Error("x")) : Promise.resolve(1);
      },
    });
    s.start();
    await flush();
    s.add({ id: "hold", run: hold.run });
    await clock.advance(5); // r ready now, after hold started
    s.add({ id: "later", run: () => (order.push("later"), Promise.resolve(1)) });
    hold.attempts[0]!.resolve(1);
    await s.onIdle();
    expect(order).toEqual(["r1", "r2", "later"]);
  });
});

describe("timeouts", () => {
  it("aborts, frees the slot and refills within the timer callback", async () => {
    const s = make(1);
    const log = record(s);
    const t = controlled();
    const next = controlled();
    s.add({ id: "t", run: t.run, timeoutMs: 50 });
    s.add({ id: "next", run: next.run });
    s.start();
    expect(clock.pending).toBe(1);
    const signal = t.attempts[0]!.ctx.signal;
    await clock.advance(50);
    expect(signal.aborted).toBe(true);
    expect(s.state("t")).toBe("failed");
    expect(next.attempts).toHaveLength(1);
    const e = await rejection(s.result("t"));
    expect(e.kind).toBe("timeout");
    expect(e.attempts).toBe(1);
    expect(signal.reason).toBe(e);
    t.attempts[0]!.resolve("late"); // ignored
    t.attempts[0]!.reject(new Error("late"));
    next.attempts[0]!.resolve(1);
    await s.onIdle();
    expect(log).toEqual(["start:t:1", "failure:t:timeout", "start:next:1", "success:next:1", "idle"]);
    expect(clock.pending).toBe(0);
  });

  it("timeouts can be retried; the retried attempt's signal reason is a timeout TaskError", async () => {
    const s = make(1);
    const log = record(s);
    const t = controlled();
    let retryErr: unknown;
    s.on("retry", (_i, _n, _d, e) => (retryErr = e));
    s.add({ id: "t", run: t.run, timeoutMs: 10, retries: 1, backoffMs: 20 });
    s.start();
    await clock.advance(10);
    const r = t.attempts[0]!.ctx.signal.reason as TaskError;
    expect(r).toBeInstanceOf(TaskError);
    expect(r.kind).toBe("timeout");
    expect(retryErr).toBe(r);
    expect(s.state("t")).toBe("retrying");
    await clock.advance(20);
    expect(t.attempts).toHaveLength(2);
    t.attempts[1]!.resolve("ok");
    expect(await s.result("t")).toBe("ok");
    expect(log).toEqual(["start:t:1", "retry:t:2:20", "start:t:2", "success:t:ok", "idle"]);
    expect(clock.pending).toBe(0);
  });

  it("final failure kind is failed when the last attempt rejected after an earlier timeout", async () => {
    const s = make(1);
    const t = controlled();
    s.add({ id: "t", run: t.run, timeoutMs: 10, retries: 1 });
    s.start();
    await clock.advance(10);
    t.attempts[1]!.reject("plain");
    const e = await rejection(s.result("t"));
    expect(e.kind).toBe("failed");
    expect(e.cause).toBe("plain");
    expect(e.attempts).toBe(2);
    expect(clock.pending).toBe(0);
  });

  it("an attempt that settles before the timeout clears its timer", async () => {
    const s = make(1);
    s.add({ id: "t", run: ok(1), timeoutMs: 1000 });
    s.start();
    expect(clock.pending).toBe(1);
    await s.onIdle();
    expect(clock.pending).toBe(0);
  });
});

describe("cancellation", () => {
  it("cancels running tasks: aborts, frees and refills the slot in the same call", async () => {
    const s = make(1);
    const log = record(s);
    const a = controlled();
    const b = controlled();
    s.add({ id: "a", run: a.run, timeoutMs: 100 });
    s.add({ id: "b", run: b.run });
    s.add({ id: "dep", deps: ["a"], run: ok(1) });
    s.start();
    const reason = { why: "user" };
    expect(s.cancel("a", reason)).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    expect(s.state("dep")).toBe("cancelled");
    expect(b.attempts).toHaveLength(1);
    expect(clock.pending).toBe(0);
    const e = await rejection(s.result("a"));
    expect(e.kind).toBe("cancelled");
    expect(e.cause).toBe(reason);
    expect(e.attempts).toBe(1);
    expect(a.attempts[0]!.ctx.signal.aborted).toBe(true);
    expect(a.attempts[0]!.ctx.signal.reason).toBe(e);
    a.attempts[0]!.reject(new Error("ignored"));
    expect(s.cancel("a")).toBe(false);
    b.attempts[0]!.resolve(1);
    await s.onIdle();
    expect(s.cancel("b")).toBe(false);
    expect(log).toEqual(["start:a:1", "cancel:a:cancelled", "cancel:dep:dependency", "start:b:1", "success:b:1", "idle"]);
  });

  it("cancels queued and retrying tasks, clearing backoff timers", async () => {
    const s = make(1);
    const r = controlled();
    s.add({ id: "r", run: r.run, retries: 2, backoffMs: 1000 });
    s.add({ id: "q", run: ok(1) });
    expect(s.cancel("q")).toBe(true);
    s.start();
    r.attempts[0]!.reject(new Error("x"));
    await flush();
    expect(s.state("r")).toBe("retrying");
    expect(clock.pending).toBe(1);
    expect(s.cancel("r")).toBe(true);
    expect(clock.pending).toBe(0);
    const e = await rejection(s.result("r"));
    expect(e.kind).toBe("cancelled");
    expect(e.attempts).toBe(1);
    expect(e.cause).toBeUndefined();
    expect((await rejection(s.result("q"))).attempts).toBe(0);
    await s.onIdle();
  });
});

describe("events, idle and robustness", () => {
  it("swallows listener exceptions and supports unsubscribing (twice)", async () => {
    const s = make(1);
    const seen: string[] = [];
    s.on("start", () => {
      throw new Error("listener");
    });
    const off = s.on("start", (id) => seen.push(id));
    s.on("success", () => {
      throw new Error("listener");
    });
    s.add({ id: "a", run: ok(1) });
    s.start();
    expect(await s.result("a")).toBe(1);
    off();
    off();
    s.add({ id: "b", run: ok(2) });
    expect(await s.result("b")).toBe(2);
    expect(seen).toEqual(["a"]);
  });

  it("idle fires once per busy->idle transition; onIdle semantics", async () => {
    const s = make(1);
    let idles = 0;
    s.on("idle", () => idles++);
    await s.onIdle(); // never started, nothing to do
    s.start();
    expect(idles).toBe(0);
    s.pause();
    s.add({ id: "a", run: ok(1) });
    let resolved = false;
    void s.onIdle().then(() => (resolved = true));
    await flush();
    expect(resolved).toBe(false); // paused with queued work is not idle
    s.start();
    await flush();
    expect(resolved).toBe(true);
    expect(idles).toBe(1);
    s.start();
    s.pause();
    s.start();
    expect(idles).toBe(1);
    s.add({ id: "b", run: ok(2) });
    await s.onIdle();
    expect(idles).toBe(2);
  });

  it("result() promises settle consistently and nothing is left unhandled", async () => {
    const s = make(2);
    s.add({ id: "f", run: () => Promise.reject(new Error("nobody listens")) });
    s.add({ id: "g", deps: ["f"], run: ok(1) });
    s.add({ id: "h", run: ok(1), timeoutMs: 5 });
    s.start();
    await s.onIdle();
    const [e1, e2] = [await rejection(s.result("f")), await rejection(s.result("f"))];
    expect(e1.kind).toBe(e2.kind);
    expect(e1.taskId).toBe("f");
    expect(e1.name).toBe("TaskError");
    expect(e1).toBeInstanceOf(Error);
    expect(clock.pending).toBe(0);
  });

  it("a listener may add work during idle and it is dispatched", async () => {
    const s = make(1);
    let added = false;
    s.on("idle", () => {
      if (!added) {
        added = true;
        s.add({ id: "again", run: ok(2) });
      }
    });
    s.add({ id: "a", run: ok(1) });
    s.start();
    await flush();
    expect(s.state("again")).toBe("succeeded");
  });
});

describe("edge cases", () => {
  it("a task cancelled during add cascades to tasks that forward-referenced it", async () => {
    const s = make(1);
    s.add({ id: "bad", run: () => Promise.reject(new Error("x")) });
    s.start();
    await flush();
    s.pause();
    s.add({ id: "fwd", deps: ["mid"], run: ok(1) }); // waits for "mid" (not yet added)
    const log = record(s);
    s.add({ id: "mid", deps: ["bad"], run: ok(1) });
    expect(log).toEqual(["cancel:mid:dependency", "cancel:fwd:dependency", "idle"]);
    const emid = await rejection(s.result("mid"));
    expect((await rejection(s.result("fwd"))).cause).toBe(emid);
  });

  it("explicit cancel of a waiting task cascades; finished tasks cannot be cancelled", async () => {
    const s = make(1);
    const log = record(s);
    s.add({ id: "root", run: ok(1) });
    s.add({ id: "w", deps: ["missing"], run: ok(1) });
    s.add({ id: "ww", deps: ["w"], run: ok(1) });
    s.start();
    await flush();
    expect(s.cancel("root")).toBe(false);
    expect(s.cancel("w")).toBe(true);
    const ew = await rejection(s.result("w"));
    const eww = await rejection(s.result("ww"));
    expect(eww.kind).toBe("dependency");
    expect(eww.cause).toBe(ew);
    expect(log).toEqual([
      "start:root:1",
      "success:root:1",
      "cancel:w:cancelled",
      "cancel:ww:dependency",
      "idle",
    ]);
  });

  it("cycles through forward references are detected", () => {
    const s = make(1);
    s.add({ id: "a", deps: ["b"], run: ok(1) });
    expect(() => s.add({ id: "b", deps: ["a"], run: ok(1) })).toThrow(CycleError);
    s.add({ id: "b", run: ok(1) });
    expect(s.state("a")).toBe("waiting");
  });

  it("no timers remain after a mixed workload", async () => {
    const s = make(2);
    let n = 0;
    s.add({ id: "flaky", retries: 3, backoffMs: 7, timeoutMs: 50, run: () => (++n < 3 ? Promise.reject(n) : Promise.resolve(n)) });
    s.add({ id: "slow", timeoutMs: 30, retries: 1, backoffMs: 5, run: () => new Promise(() => {}) });
    s.add({ id: "after", deps: ["flaky"], run: async (ctx) => ctx.deps["flaky"] });
    s.add({ id: "never", deps: ["slow"], run: ok(1) });
    s.start();
    for (let i = 0; i < 20; i++) await clock.advance(10);
    await s.onIdle();
    expect(s.state("flaky")).toBe("succeeded");
    expect(await s.result("after")).toBe(3);
    expect(s.state("slow")).toBe("failed");
    expect(s.state("never")).toBe("cancelled");
    expect(clock.pending).toBe(0);
  });
});
