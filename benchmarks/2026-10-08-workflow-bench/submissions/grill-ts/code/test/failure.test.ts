import { describe, expect, it } from "vitest";
import { TaskError } from "../src/index.js";
import { flush } from "./helpers/fake-clock.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";
import { setup } from "./helpers/setup.js";

const boom = new Error("boom");

describe("failure and dependency cascade", () => {
  expectNoUnhandledRejections();

  it("ends failed with a TaskError of kind failed carrying the cause and attempt count", async () => {
    const { s, log } = setup();
    s.add({ id: "a", run: async () => Promise.reject(boom) });
    s.start();
    const error = await s.result("a").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(TaskError);
    expect(error).toMatchObject({ taskId: "a", kind: "failed", attempts: 1, cause: boom });
    expect(s.state("a")).toBe("failed");
    expect(log).toEqual([["start", "a", 1], ["failure", "a", error], ["idle"]]);
  });

  it("treats a synchronous throw like a rejection, handled in the settle reaction", async () => {
    const { s } = setup();
    s.add({
      id: "a",
      run: () => {
        throw boom;
      },
    });
    s.start();
    expect(s.state("a")).toBe("running");
    await flush();
    expect(s.state("a")).toBe("failed");
    await expect(s.result("a")).rejects.toMatchObject({ kind: "failed", cause: boom });
  });

  it("cancels transitive dependents in add order with kind dependency, chaining the direct cause", async () => {
    const { s, log } = setup();
    let ran = false;
    s.add({ id: "grandchild", deps: ["child"], run: async () => void (ran = true) });
    s.add({ id: "root", run: async () => Promise.reject(boom) });
    s.add({ id: "child", deps: ["root"], run: async () => void (ran = true) });
    s.add({ id: "other", deps: ["child", "root"], run: async () => void (ran = true) });
    s.start();
    await flush();
    expect(ran).toBe(false);
    const [rootErr, grandErr, childErr, otherErr] = await Promise.all(
      ["root", "grandchild", "child", "other"].map((id) => s.result(id).catch((e: unknown) => e)),
    );
    expect(log).toEqual([
      ["start", "root", 1],
      ["failure", "root", rootErr],
      ["cancel", "grandchild", grandErr],
      ["cancel", "child", childErr],
      ["cancel", "other", otherErr],
      ["idle"],
    ]);
    expect(childErr).toMatchObject({ taskId: "child", kind: "dependency", attempts: 0, cause: rootErr });
    expect(grandErr).toMatchObject({ taskId: "grandchild", kind: "dependency", cause: childErr });
    // First failed dependency in deps order.
    expect(otherErr).toMatchObject({ kind: "dependency", cause: childErr });
    expect(["grandchild", "child", "other"].map((id) => s.state(id))).toEqual(["cancelled", "cancelled", "cancelled"]);
  });

  it("cancels a task during add when a dependency already failed, cascading to forward-referencing tasks", async () => {
    const { s, log } = setup();
    s.add({ id: "bad", run: async () => Promise.reject(boom) });
    s.add({ id: "fine", run: async () => 1 });
    s.start();
    await s.onIdle();
    log.length = 0;
    s.add({ id: "waiter", deps: ["late"], run: async () => 0 });
    s.add({ id: "late", deps: ["fine", "bad"], run: async () => 0 });
    const badErr = await s.result("bad").catch((e: unknown) => e);
    const lateErr = await s.result("late").catch((e: unknown) => e);
    const waiterErr = await s.result("waiter").catch((e: unknown) => e);
    expect(lateErr).toMatchObject({ kind: "dependency", attempts: 0, cause: badErr });
    expect(waiterErr).toMatchObject({ kind: "dependency", cause: lateErr });
    expect(log).toEqual([
      ["cancel", "late", lateErr],
      ["cancel", "waiter", waiterErr],
      ["idle"],
    ]);
  });

  it("emits no idle for an add that is cancelled immediately while already idle", async () => {
    const { s, log } = setup();
    s.add({ id: "bad", run: async () => Promise.reject(boom) });
    s.start();
    await s.onIdle();
    log.length = 0;
    s.add({ id: "x", deps: ["bad"], run: async () => 0 });
    await flush();
    expect(log.map((e) => e[0])).toEqual(["cancel"]);
  });

  it("never causes unhandled rejections even when nobody calls result()", async () => {
    const { s } = setup();
    s.add({ id: "a", run: async () => Promise.reject(boom) });
    s.add({ id: "b", deps: ["a"], run: async () => 0 });
    s.start();
    await s.onIdle();
  });

  it("cascades through a very deep dependency chain without exhausting the stack", async () => {
    const { s } = setup();
    const n = 20_000;
    for (let i = 0; i < n; i++) s.add({ id: `t${i}`, deps: i ? [`t${i - 1}`] : [], run: async () => 0 });
    s.cancel("t0");
    const last = await s.result(`t${n - 1}`).catch((e: unknown) => e);
    expect(last).toMatchObject({ kind: "dependency", cause: { taskId: `t${n - 2}` } });
  });
});
