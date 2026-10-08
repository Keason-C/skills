import { describe, expect, it } from "vitest";
import type { TaskSpec } from "../src/index.js";
import { flush } from "./helpers/fake-clock.js";
import { deferred, setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

expectNoUnhandledRejections();

describe("edge cases from the spec", () => {
  it("accepts a run that returns a plain value instead of a promise", async () => {
    const { s } = setup();
    s.add({ id: "a", run: (() => 7) as unknown as TaskSpec["run"] });
    s.start();
    await expect(s.result("a")).resolves.toBe(7);
  });

  it("returns the same result promise on every call", () => {
    const { s } = setup();
    s.add({ id: "a", run: async () => 1 });
    expect(s.result("a")).toBe(s.result("a"));
  });

  it("lets run cancel its own task synchronously: timeout cleared, slot freed, settle ignored", async () => {
    const { s, clock, log } = setup(1);
    s.add({
      id: "self",
      timeoutMs: 10,
      run: async () => {
        s.cancel("self", "changed my mind");
        return "ignored";
      },
    });
    s.add({ id: "next", run: async () => "n" });
    s.start();
    expect(s.state("self")).toBe("cancelled");
    expect(s.state("next")).toBe("running");
    expect(clock.pendingCount()).toBe(0);
    await flush();
    await expect(s.result("self")).rejects.toMatchObject({ kind: "cancelled", attempts: 1, cause: "changed my mind" });
    expect(log.map((e) => e.slice(0, 2))).toEqual([
      ["start", "self"],
      ["cancel", "self"],
      ["start", "next"],
      ["success", "next"],
      ["idle"],
    ]);
  });

  it("still times out a running attempt while paused", async () => {
    const { s, clock } = setup();
    s.add({ id: "a", timeoutMs: 5, run: () => new Promise(() => {}) });
    s.start();
    s.pause();
    await clock.advance(5);
    await expect(s.result("a")).rejects.toMatchObject({ kind: "timeout" });
    expect(clock.pendingCount()).toBe(0);
  });

  it("re-queues a zero-delay retry behind equal-priority tasks that were already queued", async () => {
    const { s, log } = setup(1);
    s.add({ id: "flaky", retries: 1, run: async (ctx) => (ctx.attempt === 1 ? Promise.reject(new Error("x")) : 0) });
    s.add({ id: "other", run: async () => 0 });
    s.start();
    await s.onIdle();
    expect(log.filter((e) => e[0] === "start").map((e) => e.slice(1))).toEqual([
      ["flaky", 1],
      ["other", 1],
      ["flaky", 2],
    ]);
  });

  it("keeps the scheduler busy while a task waits on an id that is never added", async () => {
    const { s } = setup();
    s.add({ id: "orphan", deps: ["ghost"], run: async () => 0 });
    s.start();
    let idle = false;
    void s.onIdle().then(() => (idle = true));
    await flush();
    expect(idle).toBe(false);
    expect(s.cancel("ghost")).toBe(false);
    s.cancel("orphan");
    await flush();
    expect(idle).toBe(true);
  });

  it("starts a dependent with the value of a dependency that resolved to undefined", async () => {
    const { s } = setup();
    const gate = deferred<undefined>();
    s.add({ id: "a", run: () => gate.promise });
    s.add({ id: "b", deps: ["a"], run: async (ctx) => Object.keys(ctx.deps) });
    s.start();
    gate.resolve(undefined);
    await expect(s.result("b")).resolves.toEqual(["a"]);
  });
});
