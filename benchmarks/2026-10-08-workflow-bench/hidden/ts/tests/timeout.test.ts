import { describe, expect, it } from "vitest";
import { errInfo, evs, flush, make, track } from "./helpers.js";

// Retried timeouts here always use backoffMs > 0 (backoff 0 is a product-owner decision).
describe("per-attempt timeouts", () => {
  it("an attempt still running after timeoutMs fails with kind timeout and its signal is aborted", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50 }));
    const r = track(s.result("a"));
    s.start();
    const signal = runs.last("a").ctx.signal;
    await clock.advance(49);
    expect(s.state("a")).toBe("running");
    expect(signal.aborted).toBe(false);
    await clock.advance(1);
    expect(signal.aborted).toBe(true);
    expect(s.state("a")).toBe("failed");
    expect(r.status).toBe("rejected");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "timeout", attempts: 1 });
  });

  it("the signal's abort event fires at the timeout moment", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50 }));
    const t0 = clock.now();
    s.start();
    const abortedAt: number[] = [];
    runs.last("a").ctx.signal.addEventListener("abort", () => abortedAt.push(clock.now()));
    await clock.advance(200);
    expect(abortedAt).toEqual([t0 + 50]);
  });

  it("the slot is released at the timeout and refilled synchronously inside the timer callback", async () => {
    const { s, runs, clock } = make(1);
    const t0 = clock.now();
    s.add(runs.task("a", { timeoutMs: 50 }));
    s.add(runs.task("b"));
    s.start();
    expect(runs.order).toEqual(["a"]);
    expect(clock.runNext()).toBe(true); // the only timer: a's timeout
    expect(clock.now()).toBe(t0 + 50);
    expect(s.state("a")).toBe("failed");
    expect(runs.order).toEqual(["a", "b"]);
    expect(s.state("b")).toBe("running");
  });

  it("a late resolve from a timed-out run is ignored", async () => {
    const { s, runs, clock, log } = make(1, { events: true });
    s.add(runs.task("a", { timeoutMs: 50 }));
    const r = track(s.result("a"));
    s.start();
    await clock.advance(50);
    runs.resolve("a", "too late");
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "timeout", attempts: 1 });
    expect(evs(log)).toEqual(["start:a:1", "failure:a", "idle"]);
  });

  it("a late reject from a timed-out run is ignored", async () => {
    const { s, runs, clock, log } = make(1, { events: true });
    s.add(runs.task("a", { timeoutMs: 50 }));
    const r = track(s.result("a"));
    s.start();
    await clock.advance(50);
    runs.reject("a", new Error("late"));
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "timeout", attempts: 1 });
    expect(evs(log)).toEqual(["start:a:1", "failure:a", "idle"]);
  });

  it("a late settle of a timed-out run does not free another slot", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50 }));
    s.add(runs.task("b"));
    s.add(runs.task("c"));
    s.start();
    await clock.advance(50);
    expect(s.state("b")).toBe("running");
    runs.callsOf("a")[0]!.d.resolve("late");
    await flush();
    expect(s.state("b")).toBe("running");
    expect(s.state("c")).toBe("queued");
    expect(runs.order).toEqual(["a", "b"]);
  });

  it("a timeout counts as a failed attempt and is retried with a fresh, non-aborted signal", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50, retries: 1, backoffMs: 10 }));
    const r = track(s.result("a"));
    s.start();
    await clock.advance(50);
    expect(s.state("a")).toBe("retrying");
    expect(runs.callsOf("a")[0]!.ctx.signal.aborted).toBe(true);
    await clock.advance(10);
    expect(s.state("a")).toBe("running");
    const second = runs.last("a");
    expect(second.attempt).toBe(2);
    expect(second.ctx.signal.aborted).toBe(false);
    second.d.resolve("ok");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(r.value).toBe("ok");
  });

  it("each attempt's timeout is measured from that attempt's start", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50, retries: 1, backoffMs: 10 }));
    const r = track(s.result("a"));
    s.start();
    await clock.advance(60); // attempt 1 times out at +50, attempt 2 starts at +60
    expect(runs.count("a")).toBe(2);
    await clock.advance(49);
    expect(s.state("a")).toBe("running");
    expect(runs.last("a").ctx.signal.aborted).toBe(false);
    await clock.advance(1);
    expect(runs.last("a").ctx.signal.aborted).toBe(true);
    expect(s.state("a")).toBe("failed");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "timeout", attempts: 2 });
  });

  it("the timeout starts when the attempt starts, not when the task is added", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b", { timeoutMs: 50 }));
    s.start();
    await clock.advance(100);
    expect(s.state("b")).toBe("queued");
    runs.resolve("a");
    await flush();
    expect(s.state("b")).toBe("running");
    await clock.advance(49);
    expect(s.state("b")).toBe("running");
    await clock.advance(1);
    expect(s.state("b")).toBe("failed");
  });

  it("final attempt rejecting after an earlier timeout gives kind failed", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50, retries: 1, backoffMs: 10 }));
    const r = track(s.result("a"));
    s.start();
    await clock.advance(60);
    runs.reject("a", new Error("plain failure"));
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "failed", attempts: 2 });
  });

  it("final attempt timing out after an earlier rejection gives kind timeout", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50, retries: 1, backoffMs: 10 }));
    const r = track(s.result("a"));
    s.start();
    await clock.advance(5);
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    await clock.advance(10);
    expect(s.state("a")).toBe("running");
    await clock.advance(50);
    expect(s.state("a")).toBe("failed");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "timeout", attempts: 2 });
  });

  it("an attempt that settles before its timeout is not aborted later", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 50 }));
    s.start();
    await clock.advance(10);
    runs.resolve("a", 1);
    await flush();
    await clock.advance(100);
    expect(runs.last("a").ctx.signal.aborted).toBe(false);
    expect(s.state("a")).toBe("succeeded");
  });

  it("a timed-out final attempt cascades to dependents (kind dependency)", async () => {
    const { s, runs, clock } = make(2);
    s.add(runs.task("a", { timeoutMs: 50 }));
    s.add(runs.task("b", { deps: ["a"] }));
    const rb = track(s.result("b"));
    s.start();
    await clock.advance(50);
    expect(s.state("b")).toBe("cancelled");
    expect(runs.count("b")).toBe(0);
    expect(errInfo(rb.error)).toEqual({ taskId: "b", kind: "dependency", attempts: 0 });
  });
});
