import { describe, expect, it } from "vitest";
import { flush } from "./helpers/fake-clock.js";
import { deferred, setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

expectNoUnhandledRejections();

describe("idle", () => {
  it("resolves onIdle in a microtask when already idle, and start() on an empty scheduler emits nothing", async () => {
    const { s, log } = setup();
    let resolved = false;
    void s.onIdle().then(() => (resolved = true));
    expect(resolved).toBe(false);
    await Promise.resolve();
    expect(resolved).toBe(true);
    s.start();
    await flush();
    expect(log).toEqual([]);
  });

  it("is not idle while paused with queued tasks", async () => {
    const { s, log } = setup();
    s.add({ id: "a", run: async () => 1 });
    let resolved = false;
    void s.onIdle().then(() => (resolved = true));
    await flush();
    expect(resolved).toBe(false);
    s.start();
    await flush();
    expect(resolved).toBe(true);
    expect(log.filter((e) => e[0] === "idle")).toHaveLength(1);
  });

  it("emits idle once per transition, after the task's events", async () => {
    const { s, log } = setup(2);
    s.add({ id: "a", run: async () => 1 });
    s.add({ id: "b", run: async () => 2 });
    s.start();
    await s.onIdle();
    s.add({ id: "c", run: async () => 3 });
    await s.onIdle();
    expect(log.map((e) => e[0])).toEqual(["start", "start", "success", "success", "idle", "start", "success", "idle"]);
  });

  it("dispatches tasks added from an idle listener", async () => {
    const { s } = setup();
    let added = false;
    s.on("idle", () => {
      if (added) return;
      added = true;
      s.add({ id: "again", run: async () => "x" });
    });
    s.add({ id: "a", run: async () => 1 });
    s.start();
    await flush();
    expect(s.state("again")).toBe("succeeded");
  });
});

describe("re-entrancy and state visibility", () => {
  it("lets run add tasks synchronously; they dispatch in the same dispatch pass", () => {
    const { s, log } = setup(2);
    s.add({
      id: "parent",
      run: async () => {
        s.add({ id: "child", run: () => new Promise(() => {}) });
        expect(s.state("child")).toBe("queued");
        return 0;
      },
    });
    s.start();
    expect(s.state("child")).toBe("running");
    expect(log.map((e) => e.slice(0, 2))).toEqual([
      ["start", "parent"],
      ["start", "child"],
    ]);
    s.cancel("child");
  });

  it("commits the whole cascade before the failure event, so listeners see the final states", async () => {
    const { s, log } = setup();
    const seen: Record<string, string> = {};
    s.on("failure", () => {
      seen.child = s.state("child");
      s.add({ id: "late", deps: ["child"], run: async () => 0 });
      seen.late = s.state("late");
    });
    s.add({ id: "root", run: async () => Promise.reject(new Error("x")) });
    s.add({ id: "child", deps: ["root"], run: async () => 0 });
    s.start();
    await flush();
    expect(seen).toEqual({ child: "cancelled", late: "cancelled" });
    // The recording listener runs first; late's cancel is emitted inline from the test's listener.
    expect(log.map((e) => e.slice(0, 2))).toEqual([
      ["start", "root"],
      ["failure", "root"],
      ["cancel", "late"],
      ["cancel", "child"],
      ["idle"],
    ]);
  });

  it("shows running inside a start listener and succeeded inside a success listener", async () => {
    const { s } = setup();
    const seen: string[] = [];
    s.on("start", (id) => void seen.push(s.state(id)));
    s.on("success", (id) => void seen.push(s.state(id)));
    s.add({ id: "a", run: async () => 1 });
    s.start();
    await flush();
    expect(seen).toEqual(["running", "succeeded"]);
  });

  it("emits the finished task's event, then cascades, then starts, then idle", async () => {
    const { s, log } = setup(1);
    const gate = deferred();
    s.add({ id: "x", run: () => gate.promise });
    s.add({ id: "dependent", deps: ["x"], run: async () => 0 });
    s.add({ id: "next", run: async () => 0 });
    s.start();
    s.cancel("x");
    await flush();
    expect(log.map((e) => e.slice(0, 2))).toEqual([
      ["start", "x"],
      ["cancel", "x"],
      ["cancel", "dependent"],
      ["start", "next"],
      ["success", "next"],
      ["idle"],
    ]);
  });
});
