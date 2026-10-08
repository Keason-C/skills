import { describe, expect, it } from "vitest";
import { errInfo, flush, make, track } from "./helpers.js";

describe("dependencies", () => {
  it("a task may depend on an id that is not added yet (forward reference) and waits for it", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    expect(s.state("b")).toBe("waiting");
    await flush();
    expect(runs.count("b")).toBe(0);
    s.add(runs.task("a"));
    expect(s.state("a")).toBe("running");
    expect(s.state("b")).toBe("waiting");
    runs.resolve("a", "A");
    await flush();
    expect(s.state("b")).toBe("running");
    expect(runs.last("b").ctx.deps).toEqual({ a: "A" });
  });

  it("a dependent waits while its dependency runs and is queued (not running) on a paused scheduler", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    expect(s.state("a")).toBe("running");
    expect(s.state("b")).toBe("waiting");
    s.pause();
    runs.resolve("a", 1);
    await flush();
    expect(s.state("b")).toBe("queued");
    expect(runs.count("b")).toBe(0);
    s.start();
    expect(s.state("b")).toBe("running");
  });

  it("a task whose dependencies already succeeded is ready immediately when added", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.resolve("a", 7);
    await flush();
    s.add(runs.task("b", { deps: ["a"] }));
    expect(runs.count("b")).toBe(1);
    expect(s.state("b")).toBe("running");
    expect(runs.last("b").ctx.deps).toEqual({ a: 7 });
  });

  it("a task waits for all of its dependencies", async () => {
    const { s, runs } = make(3);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.add(runs.task("c", { deps: ["a", "b"] }));
    s.start();
    runs.resolve("a", 1);
    await flush();
    expect(s.state("c")).toBe("waiting");
    expect(runs.count("c")).toBe(0);
    runs.resolve("b", 2);
    await flush();
    expect(s.state("c")).toBe("running");
    expect(runs.last("c").ctx.deps).toEqual({ a: 1, b: 2 });
  });

  it("diamond: the join task gets only its direct dependencies in ctx.deps", async () => {
    const { s, runs } = make(4);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c", { deps: ["a"] }));
    s.add(runs.task("d", { deps: ["b", "c"] }));
    s.start();
    runs.resolve("a", "A");
    await flush();
    expect(s.state("b")).toBe("running");
    expect(s.state("c")).toBe("running");
    expect(s.state("d")).toBe("waiting");
    runs.resolve("c", "C");
    await flush();
    expect(s.state("d")).toBe("waiting");
    runs.resolve("b", "B");
    await flush();
    expect(s.state("d")).toBe("running");
    expect(runs.last("d").ctx.deps).toEqual({ b: "B", c: "C" });
  });

  it("a failed dependency cancels its dependent, which never runs (kind dependency, 0 attempts)", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    const rb = track(s.result("b"));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(s.state("b")).toBe("cancelled");
    expect(runs.count("b")).toBe(0);
    expect(rb.status).toBe("rejected");
    expect(errInfo(rb.error)).toEqual({ taskId: "b", kind: "dependency", attempts: 0 });
  });

  it("the cascade is transitive", async () => {
    const { s, runs } = make(3);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c", { deps: ["b"] }));
    const rc = track(s.result("c"));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("b")).toBe("cancelled");
    expect(s.state("c")).toBe("cancelled");
    expect(runs.count("b") + runs.count("c")).toBe(0);
    expect(errInfo(rc.error)).toEqual({ taskId: "c", kind: "dependency", attempts: 0 });
  });

  it("cancelling a dependency cascades to its dependents", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c", { deps: ["b"] }));
    expect(s.cancel("a")).toBe(true);
    expect(s.state("a")).toBe("cancelled");
    expect(s.state("b")).toBe("cancelled");
    expect(s.state("c")).toBe("cancelled");
  });

  it("a task added after its dependency failed is cancelled immediately during add", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.reject("a");
    await flush();
    s.add(runs.task("b", { deps: ["a"] }));
    expect(s.state("b")).toBe("cancelled");
    expect(runs.count("b")).toBe(0);
    const rb = track(s.result("b"));
    await flush();
    expect(errInfo(rb.error)).toEqual({ taskId: "b", kind: "dependency", attempts: 0 });
  });

  it("a task added after its dependency was cancelled is cancelled immediately during add (even when paused)", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.cancel("a");
    s.add(runs.task("b", { deps: ["a"] }));
    expect(s.state("b")).toBe("cancelled");
    // and the cascade continues through later additions
    s.add(runs.task("c", { deps: ["b"] }));
    expect(s.state("c")).toBe("cancelled");
  });

  it("a dependency that already failed cancels the task even if another dependency was never added", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.reject("a");
    await flush();
    s.add(runs.task("b", { deps: ["ghost", "a"] }));
    expect(s.state("b")).toBe("cancelled");
  });

  it("a cascade does not affect unrelated tasks", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.add(runs.task("c"));
    s.start();
    expect(s.state("c")).toBe("queued");
    runs.reject("a");
    await flush();
    expect(s.state("b")).toBe("cancelled");
    expect(s.state("c")).toBe("running");
    runs.resolve("c", 1);
    await flush();
    expect(s.state("c")).toBe("succeeded");
  });

  it("a dependent of a retrying task keeps waiting through the backoff and runs after the retry succeeds", async () => {
    const { s, runs, clock } = make(2);
    s.add(runs.task("a", { retries: 1, backoffMs: 100 }));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(s.state("b")).toBe("waiting");
    await clock.advance(100);
    expect(s.state("a")).toBe("running");
    expect(s.state("b")).toBe("waiting");
    runs.resolve("a", "A2");
    await flush();
    expect(s.state("b")).toBe("running");
    expect(runs.last("b").ctx.deps).toEqual({ a: "A2" });
  });
});
