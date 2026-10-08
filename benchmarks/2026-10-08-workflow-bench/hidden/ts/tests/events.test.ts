import { describe, expect, it } from "vitest";
import { TaskError } from "../src/index.js";
import { drain, errInfo, evs, flush, make } from "./helpers.js";

describe("events", () => {
  it("a successful task: start (before run is invoked), then success, then idle", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.start();
    expect(log).toEqual(["start:a:1", "run:a:1"]);
    runs.resolve("a", 5);
    await flush();
    expect(log).toEqual(["start:a:1", "run:a:1", "success:a", "idle"]);
  });

  it("start and success listener arguments", async () => {
    const { s, runs, events } = make(1, { events: true });
    const value = { v: 1 };
    s.add(runs.task("a"));
    s.start();
    runs.resolve("a", value);
    await flush();
    const start = events!.raw.find((e) => e.event === "start")!;
    const success = events!.raw.find((e) => e.event === "success")!;
    expect(start.args).toEqual(["a", 1]);
    expect(success.args[0]).toBe("a");
    expect(success.args[1]).toBe(value);
  });

  it("events are emitted synchronously during the call that causes them", () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.start();
    expect(evs(log)).toEqual(["start:a:1"]);
    s.cancel("a");
    expect(evs(log)).toEqual(["start:a:1", "cancel:a", "idle"]);
  });

  it("success comes before the start events of the dependents it releases (add order)", async () => {
    const { s, runs, log } = make(3, { events: true });
    s.add(runs.task("a"));
    s.add(runs.task("c", { deps: ["a"] }));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    drain(log);
    runs.resolve("a");
    await flush();
    expect(evs(log)).toEqual(["success:a", "start:c:1", "start:b:1"]);
  });

  it("final failure: failure, then cascaded cancels in add order, then starts, then idle", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.add(runs.task("c", { deps: ["b"] })); // forward reference to b
    s.add(runs.task("d", { deps: ["a"] }));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("e"));
    s.start();
    expect(evs(drain(log))).toEqual(["start:a:1"]);
    runs.reject("a");
    await flush();
    expect(evs(drain(log))).toEqual(["failure:a", "cancel:c", "cancel:d", "cancel:b", "start:e:1"]);
    runs.resolve("e");
    await flush();
    expect(evs(log)).toEqual(["success:e", "idle"]);
  });

  it("explicit cancel of a running task: cancel, cascaded cancels, start of next, all inside cancel()", () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c"));
    s.start();
    drain(log);
    s.cancel("a");
    expect(evs(log)).toEqual(["cancel:a", "cancel:b", "start:c:1"]);
  });

  it("a timed-out final attempt: failure, cascaded cancel, then start of the next task", async () => {
    const { s, runs, clock, log } = make(1, { events: true });
    s.add(runs.task("a", { timeoutMs: 50 }));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c"));
    s.start();
    drain(log);
    clock.runNext();
    expect(evs(log)).toEqual(["failure:a", "cancel:b", "start:c:1"]);
  });

  it("a failed attempt that will be retried emits retry, not failure; the next attempt emits start", async () => {
    const { s, runs, clock, log, events } = make(1, { events: true });
    s.add(runs.task("a", { retries: 1, backoffMs: 100 }));
    s.start();
    drain(log);
    runs.reject("a");
    await flush();
    expect(evs(drain(log))).toEqual(["retry:a:2:100"]);
    expect(events!.raw.find((e) => e.event === "retry")!.args.slice(0, 3)).toEqual(["a", 2, 100]);
    await clock.advance(100);
    expect(evs(drain(log))).toEqual(["start:a:2"]);
    runs.resolve("a");
    await flush();
    expect(evs(log)).toEqual(["success:a", "idle"]);
  });

  it("failure and cancel listeners receive TaskErrors", async () => {
    const { s, runs, events } = make(1, { events: true });
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("x"));
    s.start();
    runs.reject("a");
    await flush();
    s.cancel("x");
    const failure = events!.raw.find((e) => e.event === "failure")!;
    expect(failure.args[0]).toBe("a");
    expect(failure.args[1]).toBeInstanceOf(TaskError);
    expect(errInfo(failure.args[1])).toEqual({ taskId: "a", kind: "failed", attempts: 1 });
    const cancels = events!.raw.filter((e) => e.event === "cancel");
    expect(cancels.map((c) => c.args[0])).toEqual(["b", "x"]);
    expect(errInfo(cancels[0]!.args[1])).toEqual({ taskId: "b", kind: "dependency", attempts: 0 });
    expect(errInfo(cancels[1]!.args[1])).toEqual({ taskId: "x", kind: "cancelled", attempts: 1 });
  });

  it("idle fires once when the last task finishes, not after each task", async () => {
    const { s, runs, log } = make(2, { events: true });
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    runs.resolve("a");
    await flush();
    expect(log.filter((l) => l === "idle")).toEqual([]);
    runs.resolve("b");
    await flush();
    expect(evs(log)).toEqual(["start:a:1", "start:b:1", "success:a", "success:b", "idle"]);
  });

  it("the unsubscribe function returned by on() stops further calls", async () => {
    const { s, runs } = make(1);
    const seen: string[] = [];
    const off = s.on("start", (id) => seen.push(id));
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    expect(seen).toEqual(["a"]);
    off();
    runs.resolve("a");
    await flush();
    expect(runs.order).toEqual(["a", "b"]);
    expect(seen).toEqual(["a"]);
  });

  it("several listeners for the same event are all called", () => {
    const { s, runs } = make(1);
    const one: string[] = [];
    const two: string[] = [];
    s.on("start", (id) => one.push(id));
    s.on("start", (id) => two.push(id));
    s.add(runs.task("a"));
    s.start();
    expect(one).toEqual(["a"]);
    expect(two).toEqual(["a"]);
  });

  it("a task cancelled during add (dependency already failed) emits its cancel event during add", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.start();
    runs.reject("a");
    await flush();
    drain(log);
    s.add(runs.task("b", { deps: ["a"] }));
    expect(evs(log).filter((l) => l !== "idle")).toEqual(["cancel:b"]);
  });

  it("the task's state is already final when its success / failure / cancel event fires", async () => {
    const { s, runs } = make(2);
    const seen: string[] = [];
    s.on("success", (id) => seen.push(`${id}=${s.state(id)}`));
    s.on("failure", (id) => seen.push(`${id}=${s.state(id)}`));
    s.on("cancel", (id) => seen.push(`${id}=${s.state(id)}`));
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.add(runs.task("c", { deps: ["b"] }));
    s.start();
    runs.resolve("a");
    await flush();
    runs.reject("b");
    await flush();
    expect(seen).toEqual(["a=succeeded", "b=failed", "c=cancelled"]);
  });
});
