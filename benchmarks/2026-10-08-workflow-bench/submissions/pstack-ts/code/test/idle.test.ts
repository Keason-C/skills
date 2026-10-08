import { describe, expect, test } from "vitest";
import { controlled, instant, scripted, setup, taskError } from "./harness.js";

const noop = () => Promise.resolve(undefined);

async function settledSoon(p: Promise<void>, flush: () => Promise<void>): Promise<boolean> {
  let done = false;
  void p.then(() => {
    done = true;
  });
  await flush();
  return done;
}

describe("idle event (rule 9)", () => {
  test("no idle on start() of an empty scheduler", async () => {
    const { s, take, flush } = setup();
    s.start();
    await flush();
    expect(take()).toEqual([]);
  });

  test("no idle on pause() or a second start() of an idle scheduler", async () => {
    const { s, take, flush } = setup();
    instant(s, "A");
    s.start();
    await flush();
    expect(take()).toEqual([["start", "A", 1], ["success", "A", "A"], ["idle"]]);
    s.pause();
    s.start();
    await flush();
    expect(take()).toEqual([]);
  });

  test("add that cancels immediately on an idle scheduler emits only cancel", async () => {
    const { s, take, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("x") }]);
    s.start();
    await flush();
    take();
    s.add({ id: "C", run: noop, deps: ["A"] });
    await flush();
    expect(take()).toEqual([["cancel", "C", taskError("C", "dependency", 0, expect.anything())]]);
  });

  test("add then cancel: idle fires from the cancel call", async () => {
    const { s, take, flush } = setup();
    s.start();
    controlled(s, { id: "A" });
    expect(take()).toEqual([["start", "A", 1]]);
    s.cancel("A");
    expect(take()).toEqual([["cancel", "A", taskError("A", "cancelled", 1, undefined)], ["idle"]]);
    await flush();
    expect(take()).toEqual([]);
  });

  test("idle fires once per busy -> idle transition", async () => {
    const { s, take, flush } = setup();
    instant(s, "A");
    s.start();
    await flush();
    expect(take().filter((e) => e[0] === "idle")).toHaveLength(1);
    instant(s, "B");
    instant(s, "C");
    await flush();
    expect(take()).toEqual([
      ["start", "B", 1],
      ["success", "B", "B"],
      ["start", "C", 1],
      ["success", "C", "C"],
      ["idle"],
    ]);
  });

  test("pausing a busy scheduler is not idle: queued tasks keep it busy", async () => {
    const { s, take, flush } = setup();
    controlled(s, { id: "A" });
    s.pause();
    await flush();
    expect(take()).toEqual([]);
    expect(await settledSoon(s.onIdle(), flush)).toBe(false);
  });

  test("a task waiting on a forward reference keeps the scheduler busy", async () => {
    const { s, take, flush } = setup();
    s.add({ id: "B", run: noop, deps: ["MISSING"] });
    s.start();
    expect(await settledSoon(s.onIdle(), flush)).toBe(false);
    expect(take()).toEqual([]);
    s.cancel("B");
    expect(take()).toEqual([["cancel", "B", taskError("B", "cancelled", 0, undefined)], ["idle"]]);
  });

  test("a retrying task keeps the scheduler busy until it finishes", async () => {
    const { s, clock, take, flush } = setup();
    scripted(s, { id: "A", retries: 1, backoffMs: 50 }, [{ reject: new Error("x") }, { ok: 1 }]);
    s.start();
    await flush();
    expect(take().filter((e) => e[0] === "idle")).toEqual([]);
    const idle = s.onIdle();
    expect(await settledSoon(idle, flush)).toBe(false);
    await clock.advance(50);
    expect(take()).toEqual([["start", "A", 2], ["success", "A", 1], ["idle"]]);
    expect(await settledSoon(idle, flush)).toBe(true);
  });

  test("cancelling a waiting dependent while its dependency runs does not idle until the dependency finishes", async () => {
    const { s, take, flush } = setup({ concurrency: 1 });
    const a = controlled(s, { id: "A" });
    controlled(s, { id: "B", deps: ["A"] });
    s.start();
    take();
    s.cancel("B");
    expect(take()).toEqual([["cancel", "B", taskError("B", "cancelled", 0, undefined)]]);
    a.resolve(1);
    await flush();
    expect(take()).toEqual([["success", "A", 1], ["idle"]]);
  });
});

describe("onIdle()", () => {
  test("resolves in a microtask when the scheduler is already idle", async () => {
    const { s, flush } = setup();
    expect(await settledSoon(s.onIdle(), flush)).toBe(true);
    s.start();
    expect(await settledSoon(s.onIdle(), flush)).toBe(true);
  });

  test("resolves once the last task finishes; several waiters all resolve", async () => {
    const { s, flush } = setup({ concurrency: 2 });
    const a = controlled(s, { id: "A" });
    const b = controlled(s, { id: "B" });
    s.start();
    const w1 = s.onIdle();
    const w2 = s.onIdle();
    expect(await settledSoon(w1, flush)).toBe(false);
    a.resolve(1);
    await flush();
    expect(await settledSoon(w1, flush)).toBe(false);
    b.resolve(2);
    await flush();
    expect(await settledSoon(w1, flush)).toBe(true);
    expect(await settledSoon(w2, flush)).toBe(true);
  });

  test("stays pending while a task is queued on a paused scheduler", async () => {
    const { s, clock, flush } = setup();
    controlled(s, { id: "A" });
    const idle = s.onIdle();
    await clock.advance(10_000);
    expect(await settledSoon(idle, flush)).toBe(false);
    s.cancel("A");
    expect(await settledSoon(idle, flush)).toBe(true);
  });

  test("resolves immediately again after the scheduler returned to idle", async () => {
    const { s, flush } = setup();
    instant(s, "A");
    s.start();
    await s.onIdle();
    expect(s.state("A")).toBe("succeeded");
    expect(await settledSoon(s.onIdle(), flush)).toBe(true);
  });

  test("resolves after a cascade leaves nothing unfinished", async () => {
    const { s, flush } = setup();
    scripted(s, { id: "A" }, [{ reject: new Error("x") }]);
    controlled(s, { id: "B", deps: ["A"] });
    controlled(s, { id: "C", deps: ["B"] });
    const idle = s.onIdle();
    s.start();
    await flush();
    expect(await settledSoon(idle, flush)).toBe(true);
    expect([s.state("A"), s.state("B"), s.state("C")]).toEqual(["failed", "cancelled", "cancelled"]);
  });

  test("a waiter registered inside an idle listener resolves without more work", async () => {
    const { s, flush } = setup();
    let inner: Promise<void> | undefined;
    s.on("idle", () => {
      inner = s.onIdle();
    });
    instant(s, "A");
    s.start();
    await flush();
    expect(inner).toBeDefined();
    expect(await settledSoon(inner as Promise<void>, flush)).toBe(true);
  });
});
