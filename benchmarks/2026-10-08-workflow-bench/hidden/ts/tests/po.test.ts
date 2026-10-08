// Tests whose expected outcome depends on a product-owner decision (clarifications.md) that the
// brief does not fix. Each describe block names the decision number it relies on.
import { describe, expect, it } from "vitest";
import { CycleError, TaskError } from "../src/index.js";
import { errInfo, evs, flush, make, track } from "./helpers.js";

function caught(fn: () => void): unknown {
  try {
    fn();
  } catch (e) {
    return e;
  }
  return undefined;
}

describe("PO 1: backoff 0 means synchronous re-queue, no timer", () => {
  it("backoffMs 0: retry event with delayMs 0, no timer created, attempt 2 starts right after", async () => {
    const { s, runs, clock, log } = make(1, { events: true });
    s.add(runs.task("a", { retries: 1, backoffMs: 0 }));
    s.start();
    runs.reject("a");
    await flush();
    expect(evs(log)).toEqual(["start:a:1", "retry:a:2:0", "start:a:2"]);
    expect(runs.count("a")).toBe(2);
    expect(clock.created).toBe(0);
    expect(s.state("a")).toBe("running");
  });

  it("default backoff with several retries: every delay is 0 and no timer is ever created", async () => {
    const { s, runs, clock, events } = make(1, { events: true });
    s.add(runs.task("a", { retries: 2 }));
    const r = track(s.result("a"));
    s.start();
    runs.reject("a");
    await flush();
    runs.reject("a");
    await flush();
    runs.reject("a");
    await flush();
    expect(events!.raw.filter((e) => e.event === "retry").map((e) => e.args.slice(0, 3))).toEqual([
      ["a", 2, 0],
      ["a", 3, 0],
    ]);
    expect(clock.created).toBe(0);
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "failed", attempts: 3 });
  });

  it("backoff 0: the re-queued task goes behind tasks that were ready earlier", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 0 }));
    s.add(runs.task("b"));
    s.start();
    runs.reject("a");
    await flush();
    expect(runs.order).toEqual(["a", "b"]);
    expect(s.state("a")).toBe("queued");
    runs.resolve("b");
    await flush();
    expect(runs.order).toEqual(["a", "b", "a"]);
    expect(runs.last("a").attempt).toBe(2);
  });
});

describe("PO 2: listener exceptions are swallowed", () => {
  it("a throwing start listener does not stop other listeners, the run, or start()", () => {
    const { s, runs } = make(1);
    const seen: string[] = [];
    s.on("start", () => {
      throw new Error("listener boom");
    });
    s.on("start", (id) => seen.push(id));
    s.add(runs.task("a"));
    expect(() => s.start()).not.toThrow();
    expect(seen).toEqual(["a"]);
    expect(runs.count("a")).toBe(1);
    expect(s.state("a")).toBe("running");
  });

  it("a throwing success listener does not affect the scheduler", async () => {
    const { s, runs } = make(1);
    const idles: number[] = [];
    s.on("success", () => {
      throw new Error("listener boom");
    });
    s.on("idle", () => idles.push(1));
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    runs.resolve("a", "A");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(s.state("b")).toBe("running");
    await expect(s.result("a")).resolves.toBe("A");
    runs.resolve("b", "B");
    await flush();
    expect(s.state("b")).toBe("succeeded");
    expect(idles).toEqual([1]);
  });

  it("a throwing cancel listener does not break cancel() or its cascade", () => {
    const { s, runs } = make(1);
    s.on("cancel", () => {
      throw new Error("listener boom");
    });
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c"));
    s.start();
    let ret: boolean | undefined;
    expect(() => {
      ret = s.cancel("a");
    }).not.toThrow();
    expect(ret).toBe(true);
    expect(s.state("b")).toBe("cancelled");
    expect(s.state("c")).toBe("running");
  });

  it("unsubscribing twice is harmless and leaves other listeners subscribed", () => {
    const { s, runs } = make(2);
    const one: string[] = [];
    const two: string[] = [];
    const off1 = s.on("start", (id) => one.push(id));
    s.on("start", (id) => two.push(id));
    off1();
    expect(() => off1()).not.toThrow();
    s.add(runs.task("a"));
    s.start();
    expect(one).toEqual([]);
    expect(two).toEqual(["a"]);
  });
});

describe("PO 3: result()", () => {
  it("result() for an id never added throws an Error synchronously", () => {
    const { s } = make(1);
    expect(() => s.result("nope")).toThrow(Error);
  });

  it("several result() calls settle the same way", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("ok"));
    s.add(runs.task("bad"));
    const ok1 = track(s.result("ok"));
    const bad1 = track(s.result("bad"));
    s.start();
    const ok2 = track(s.result("ok"));
    const bad2 = track(s.result("bad"));
    runs.resolve("ok", "v");
    runs.reject("bad");
    await flush();
    expect([ok1.value, ok2.value]).toEqual(["v", "v"]);
    expect(errInfo(bad1.error)).toEqual({ taskId: "bad", kind: "failed", attempts: 1 });
    expect(errInfo(bad2.error)).toEqual({ taskId: "bad", kind: "failed", attempts: 1 });
  });
});

describe("PO 4: onIdle / idle edge rules", () => {
  it("onIdle() on a scheduler with no tasks resolves even if never started", async () => {
    const { s } = make(1);
    const p = track(s.onIdle());
    await flush();
    expect(p.status).toBe("fulfilled");
  });

  it("a paused scheduler with queued tasks is not idle", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    const p = track(s.onIdle());
    await flush();
    expect(p.settled).toBe(false);
    s.start();
    runs.resolve("a");
    await flush();
    expect(p.status).toBe("fulfilled");
  });

  it("a task waiting on a dependency that is never added keeps the scheduler busy", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a", { deps: ["ghost"] }));
    s.start();
    const p = track(s.onIdle());
    await flush();
    expect(p.settled).toBe(false);
    expect(log).toEqual([]);
    s.cancel("a");
    await flush();
    expect(p.status).toBe("fulfilled");
    expect(log).toEqual(["cancel:a", "idle"]);
  });

  it("no idle event on construction or on start() of an empty scheduler", async () => {
    const { s, log } = make(1, { events: true });
    await flush();
    s.start();
    await flush();
    expect(log).toEqual([]);
  });

  it("no repeated idle event while already idle", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.start();
    runs.resolve("a");
    await flush();
    expect(log.filter((l) => l === "idle").length).toBe(1);
    s.pause();
    s.start();
    s.cancel("a");
    s.cancel("unknown");
    await s.onIdle();
    await flush();
    expect(log.filter((l) => l === "idle").length).toBe(1);
  });

  it("cancelling the last queued task of a paused scheduler emits idle", () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.cancel("a");
    expect(log).toEqual(["cancel:a", "idle"]);
  });
});

describe("PO 5: cancelling a retrying task clears its backoff timer", () => {
  it("the backoff timer is cleared by cancel()", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 100 }));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(clock.pending).toBeGreaterThan(0);
    s.cancel("a");
    expect(clock.pending).toBe(0);
  });
});

describe("PO 7: TaskError details", () => {
  it("TaskError is an Error named TaskError", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    const r = track(s.result("a"));
    s.start();
    runs.reject("a");
    await flush();
    expect(r.error).toBeInstanceOf(Error);
    expect(r.error).toBeInstanceOf(TaskError);
    expect((r.error as TaskError).name).toBe("TaskError");
  });

  it("kind failed: cause is what the last attempt rejected with; attempts = attempts started", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 2, backoffMs: 10 }));
    const r = track(s.result("a"));
    s.start();
    const errs = [new Error("e1"), new Error("e2"), new Error("e3")];
    for (const e of errs) {
      runs.reject("a", e);
      await flush();
      await clock.advance(1000);
    }
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "failed", attempts: 3 });
    expect((r.error as TaskError).cause).toBe(errs[2]);
  });

  it("kind failed: cause is what a synchronously throwing run threw", async () => {
    const { s } = make(1);
    const thrown = { custom: "thrown value" };
    s.add({
      id: "a",
      run: () => {
        throw thrown;
      },
    });
    const r = track(s.result("a"));
    s.start();
    await flush();
    expect((r.error as TaskError).cause).toBe(thrown);
  });

  it("kind cancelled: cause is the reason passed to cancel (undefined if none); attempts 0 if never started", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    const ra = track(s.result("a"));
    const rb = track(s.result("b"));
    const reason = { why: "user abort" };
    s.cancel("a", reason);
    s.cancel("b");
    await flush();
    expect(errInfo(ra.error)).toEqual({ taskId: "a", kind: "cancelled", attempts: 0 });
    expect((ra.error as TaskError).cause).toBe(reason);
    expect(errInfo(rb.error)).toEqual({ taskId: "b", kind: "cancelled", attempts: 0 });
    expect((rb.error as TaskError).cause).toBeUndefined();
  });

  it("kind cancelled: attempts counts the attempts started so far", async () => {
    const { s, runs, clock } = make(2);
    s.add(runs.task("r", { retries: 3, backoffMs: 10 }));
    s.add(runs.task("x", { retries: 3, backoffMs: 10 }));
    const rr = track(s.result("r"));
    const rx = track(s.result("x"));
    s.start();
    runs.reject("r");
    runs.reject("x");
    await flush();
    await clock.advance(10);
    // r: attempt 2 running; x: attempt 2 running -> fail x again so it is retrying
    runs.reject("x");
    await flush();
    expect(s.state("r")).toBe("running");
    expect(s.state("x")).toBe("retrying");
    s.cancel("r", "stop r");
    s.cancel("x", "stop x");
    await flush();
    expect(errInfo(rr.error)).toEqual({ taskId: "r", kind: "cancelled", attempts: 2 });
    expect((rr.error as TaskError).cause).toBe("stop r");
    expect(errInfo(rx.error)).toEqual({ taskId: "x", kind: "cancelled", attempts: 2 });
    expect((rx.error as TaskError).cause).toBe("stop x");
  });

  it("kind dependency: cause is the direct dependency's TaskError (A -> B -> C chain)", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("A"));
    s.add(runs.task("B", { deps: ["A"] }));
    s.add(runs.task("C", { deps: ["B"] }));
    const rb = track(s.result("B"));
    const rc = track(s.result("C"));
    s.start();
    runs.reject("A", new Error("A broke"));
    await flush();
    expect(errInfo(rb.error)).toEqual({ taskId: "B", kind: "dependency", attempts: 0 });
    const bCause = (rb.error as TaskError).cause;
    expect(errInfo(bCause)).toEqual({ taskId: "A", kind: "failed", attempts: 1 });
    expect(errInfo(rc.error)).toEqual({ taskId: "C", kind: "dependency", attempts: 0 });
    const cCause = (rc.error as TaskError).cause;
    expect(errInfo(cCause)).toEqual({ taskId: "B", kind: "dependency", attempts: 0 });
    expect(errInfo((cCause as TaskError).cause)).toEqual({ taskId: "A", kind: "failed", attempts: 1 });
  });

  it("kind dependency: cause names the dependency that failed, among several", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("ok"));
    s.add(runs.task("bad"));
    s.add(runs.task("join", { deps: ["ok", "bad"] }));
    const r = track(s.result("join"));
    s.start();
    runs.resolve("ok");
    await flush();
    runs.reject("bad");
    await flush();
    expect(errInfo(r.error)).toEqual({ taskId: "join", kind: "dependency", attempts: 0 });
    expect(errInfo((r.error as TaskError).cause)).toEqual({ taskId: "bad", kind: "failed", attempts: 1 });
  });

  it("kind dependency: for a task added after its dependency was cancelled, cause is that TaskError", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.cancel("a", "why");
    s.add(runs.task("b", { deps: ["a"] }));
    const r = track(s.result("b"));
    await flush();
    expect(errInfo(r.error)).toEqual({ taskId: "b", kind: "dependency", attempts: 0 });
    const cause = (r.error as TaskError).cause;
    expect(errInfo(cause)).toEqual({ taskId: "a", kind: "cancelled", attempts: 0 });
    expect((cause as TaskError).cause).toBe("why");
  });

  it("kind timeout: attempts counts every attempt started", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 10, timeoutMs: 20 }));
    const r = track(s.result("a"));
    s.start();
    await clock.advance(20); // attempt 1 times out
    await clock.advance(10); // attempt 2 starts
    await clock.advance(20); // attempt 2 times out
    expect(runs.count("a")).toBe(2);
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "timeout", attempts: 2 });
  });

  it("ctx.signal.reason of a cancelled running attempt is its cancelled TaskError", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    const reason = new Error("stop");
    s.cancel("a", reason);
    const sr = runs.last("a").ctx.signal.reason;
    expect(errInfo(sr)).toEqual({ taskId: "a", kind: "cancelled", attempts: 1 });
    expect((sr as TaskError).cause).toBe(reason);
  });

  it("ctx.signal.reason of a timed-out final attempt is a TaskError of kind timeout", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 30 }));
    s.start();
    await clock.advance(30);
    const sr = runs.last("a").ctx.signal.reason;
    expect(sr).toBeInstanceOf(TaskError);
    expect((sr as TaskError).kind).toBe("timeout");
    expect((sr as TaskError).taskId).toBe("a");
  });

  it("ctx.signal.reason of a timed-out attempt that will be retried is a TaskError of kind timeout", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 30, retries: 1, backoffMs: 50 }));
    s.start();
    await clock.advance(30);
    expect(s.state("a")).toBe("retrying");
    const sr = runs.callsOf("a")[0]!.ctx.signal.reason;
    expect(sr).toBeInstanceOf(TaskError);
    expect((sr as TaskError).kind).toBe("timeout");
    expect((sr as TaskError).taskId).toBe("a");
  });
});

describe("PO 8: option validation", () => {
  it.each([Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, Number.NaN])(
    "priority %s is rejected with a RangeError",
    (priority) => {
      const { s, runs } = make(1);
      expect(() => s.add(runs.task("a", { priority }))).toThrow(RangeError);
    },
  );

  it.each([-1, 1.5])("retries %s is rejected with a RangeError", (retries) => {
    const { s, runs } = make(1);
    expect(() => s.add(runs.task("a", { retries }))).toThrow(RangeError);
  });

  it("negative backoffMs is rejected with a RangeError", () => {
    const { s, runs } = make(1);
    expect(() => s.add(runs.task("a", { backoffMs: -1 }))).toThrow(RangeError);
  });

  it.each([0, -10])("timeoutMs %s is rejected with a RangeError", (timeoutMs) => {
    const { s, runs } = make(1);
    expect(() => s.add(runs.task("a", { timeoutMs }))).toThrow(RangeError);
  });
});

describe("PO 9: cancelling a task waiting on never-added dependencies", () => {
  it("returns true and the task ends cancelled", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a", { deps: ["ghost"] }));
    const r = track(s.result("a"));
    expect(s.cancel("a")).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    await flush();
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "cancelled", attempts: 0 });
  });
});

describe("PO 10: CycleError details", () => {
  it("CycleError is an Error named CycleError; a self-dependency gives [id]", () => {
    const { s, runs } = make(1);
    const e = caught(() => s.add(runs.task("a", { deps: ["a"] })));
    expect(e).toBeInstanceOf(CycleError);
    expect(e).toBeInstanceOf(Error);
    expect((e as CycleError).name).toBe("CycleError");
    expect((e as CycleError).cycle).toEqual(["a"]);
  });

  it("cycle contains exactly the ids on the cycle, each once", () => {
    const { s, runs } = make(1);
    s.add(runs.task("x", { deps: ["a"] }));
    s.add(runs.task("a", { deps: ["b"] }));
    s.add(runs.task("b", { deps: ["c"] }));
    s.add(runs.task("z"));
    const e = caught(() => s.add(runs.task("c", { deps: ["z", "a"] })));
    expect(e).toBeInstanceOf(CycleError);
    expect([...(e as CycleError).cycle].sort()).toEqual(["a", "b", "c"]);
  });
});

describe("PO 11: refill order after a timeout that is retried", () => {
  it("retry event first, then the freed slot is refilled, all inside the timer callback", () => {
    const { s, runs, clock, log } = make(1, { events: true });
    s.add(runs.task("a", { timeoutMs: 50, retries: 1, backoffMs: 100 }));
    s.add(runs.task("b"));
    s.start();
    expect(evs(log)).toEqual(["start:a:1"]);
    clock.runNext(); // a's timeout
    expect(evs(log)).toEqual(["start:a:1", "retry:a:2:100", "start:b:1"]);
    expect(s.state("a")).toBe("retrying");
    expect(s.state("b")).toBe("running");
  });
});

describe("PO 12: start/pause idempotence", () => {
  it("start() while started does nothing extra", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    s.start();
    expect(evs(log)).toEqual(["start:a:1"]);
    expect(runs.order).toEqual(["a"]);
    runs.resolve("a");
    await flush();
    s.start();
    expect(runs.order).toEqual(["a", "b"]);
    expect(s.state("b")).toBe("running");
  });

  it("pause() while paused does nothing; a single start() then resumes", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.pause();
    s.pause();
    expect(s.state("a")).toBe("queued");
    s.start();
    expect(s.state("a")).toBe("running");
    s.pause();
    s.pause();
    s.add(runs.task("b"));
    runs.resolve("a");
    await flush();
    expect(s.state("b")).toBe("queued");
    s.start();
    expect(s.state("b")).toBe("running");
  });
});
