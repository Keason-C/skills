import { describe, expect, it } from "vitest";
import { errInfo, evs, flush, make, track } from "./helpers.js";

describe("cancellation", () => {
  it("cancelling a queued task returns true, ends cancelled, and it never runs", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    const r = track(s.result("a"));
    expect(s.cancel("a")).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    s.start();
    await flush();
    expect(runs.count("a")).toBe(0);
    expect(r.status).toBe("rejected");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "cancelled", attempts: 0 });
  });

  it("cancelling a running task aborts its signal and frees its slot immediately", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    const signal = runs.last("a").ctx.signal;
    expect(s.cancel("a")).toBe(true);
    expect(signal.aborted).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    expect(s.state("b")).toBe("running");
    expect(runs.order).toEqual(["a", "b"]);
  });

  it("whatever a cancelled running task later settles with is ignored", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    const r = track(s.result("a"));
    s.start();
    s.cancel("a");
    runs.resolve("a", "late value");
    await flush();
    expect(s.state("a")).toBe("cancelled");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "cancelled", attempts: 1 });
    expect(evs(log)).toEqual(["start:a:1", "cancel:a", "idle"]);
  });

  it("a cancelled running task that later rejects changes nothing", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.start();
    s.cancel("a");
    runs.reject("a", new Error("late"));
    await flush();
    expect(s.state("a")).toBe("cancelled");
    expect(evs(log)).toEqual(["start:a:1", "cancel:a", "idle"]);
  });

  it("the late settle of a cancelled running task does not free another slot", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.add(runs.task("c"));
    s.start();
    s.cancel("a");
    expect(s.state("b")).toBe("running");
    runs.callsOf("a")[0]!.d.resolve(1);
    await flush();
    expect(s.state("b")).toBe("running");
    expect(s.state("c")).toBe("queued");
  });

  it("cancelling a waiting task (dependency still running) returns true and it never runs", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    expect(s.state("b")).toBe("waiting");
    expect(s.cancel("b")).toBe(true);
    expect(s.state("b")).toBe("cancelled");
    runs.resolve("a", 1);
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(s.state("b")).toBe("cancelled");
    expect(runs.count("b")).toBe(0);
  });

  it("cancelling a retrying task returns true and it never runs again", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 2, backoffMs: 100 }));
    const r = track(s.result("a"));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(s.cancel("a")).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    await clock.advance(1000);
    expect(runs.count("a")).toBe(1);
    expect(s.state("a")).toBe("cancelled");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "cancelled", attempts: 1 });
  });

  it("cancel returns false for finished tasks and leaves their state alone", async () => {
    const { s, runs } = make(3);
    s.add(runs.task("ok"));
    s.add(runs.task("bad"));
    s.add(runs.task("gone"));
    s.start();
    runs.resolve("ok", 1);
    runs.reject("bad");
    s.cancel("gone");
    await flush();
    expect(s.cancel("ok")).toBe(false);
    expect(s.cancel("bad")).toBe(false);
    expect(s.cancel("gone")).toBe(false);
    expect(s.state("ok")).toBe("succeeded");
    expect(s.state("bad")).toBe("failed");
    expect(s.state("gone")).toBe("cancelled");
    await expect(s.result("ok")).resolves.toBe(1);
  });

  it("cancel returns false for unknown ids", () => {
    const { s } = make(1);
    expect(s.cancel("nope")).toBe(false);
    s.start();
    expect(s.cancel("nope")).toBe(false);
  });

  it("cancel cascades transitively to dependents (kind dependency)", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c", { deps: ["b"] }));
    const rb = track(s.result("b"));
    const rc = track(s.result("c"));
    s.start();
    s.cancel("a");
    expect(s.state("b")).toBe("cancelled");
    expect(s.state("c")).toBe("cancelled");
    await flush();
    expect(errInfo(rb.error)).toEqual({ taskId: "b", kind: "dependency", attempts: 0 });
    expect(errInfo(rc.error)).toEqual({ taskId: "c", kind: "dependency", attempts: 0 });
    expect(runs.order).toEqual(["a"]);
  });

  it("cancelling a running task on a paused scheduler does not start queued tasks", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    s.pause();
    expect(s.cancel("a")).toBe(true);
    await flush();
    expect(s.state("b")).toBe("queued");
    expect(runs.count("b")).toBe(0);
    s.start();
    expect(s.state("b")).toBe("running");
  });

  it("cancelling one task does not affect unrelated tasks", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    s.cancel("a");
    runs.resolve("b", "B");
    await flush();
    expect(s.state("b")).toBe("succeeded");
    await expect(s.result("b")).resolves.toBe("B");
  });
});
