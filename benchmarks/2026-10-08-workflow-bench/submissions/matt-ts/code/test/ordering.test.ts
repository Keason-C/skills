import { describe, expect, it } from "vitest";
import { Scheduler } from "../src/index.js";
import { FakeClock, deferred, flush, never } from "./helpers.js";

function recorder(s: Scheduler) {
  const starts: string[] = [];
  s.on("start", (id) => starts.push(id));
  return starts;
}

describe("concurrency and ordering", () => {
  it("never runs more than `concurrency` tasks at once", async () => {
    const s = new Scheduler({ concurrency: 2, clock: new FakeClock() });
    let running = 0;
    let peak = 0;
    const gates = Array.from({ length: 5 }, () => deferred());
    gates.forEach((g, i) =>
      s.add({
        id: `t${i}`,
        run: async () => {
          running++;
          peak = Math.max(peak, running);
          await g.promise;
          running--;
        },
      }),
    );
    s.start();
    expect(running).toBe(2);
    for (const g of gates) {
      g.resolve(undefined);
      await flush();
    }
    await s.onIdle();
    expect(peak).toBe(2);
  });

  it("starts higher priority first, then ready order, then add order", () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    const starts = recorder(s);
    s.add({ id: "low", priority: -1, run: never });
    s.add({ id: "mid1", run: never });
    s.add({ id: "high", priority: 2.5, run: never });
    s.add({ id: "mid2", run: never });
    s.start();
    expect(starts).toEqual(["high"]);
    s.cancel("high");
    s.cancel("mid1");
    s.cancel("mid2");
    expect(starts).toEqual(["high", "mid1", "mid2", "low"]);
  });

  it("orders equal-priority tasks by when they became ready, not by add order", async () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    const starts = recorder(s);
    const c = deferred();
    s.add({ id: "c", run: () => c.promise });
    s.add({ id: "e", deps: ["c"], run: async () => {} });
    s.add({ id: "d", run: async () => {} });
    s.start();
    c.resolve(1);
    await s.onIdle();
    expect(starts).toEqual(["c", "d", "e"]);
  });

  it("orders tasks made ready by the same transition by add order", async () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    const starts = recorder(s);
    const root = deferred();
    s.add({ id: "z", deps: ["root"], run: async () => {} });
    s.add({ id: "root", run: () => root.promise });
    s.add({ id: "y", deps: ["root"], run: async () => {} });
    s.add({ id: "x", deps: ["root"], priority: 1, run: async () => {} });
    s.start();
    root.resolve(1);
    await s.onIdle();
    expect(starts).toEqual(["root", "x", "z", "y"]);
  });

  it("releases a slot when a task settles and starts the next in the same reaction", async () => {
    const s = new Scheduler({ concurrency: 1, clock: new FakeClock() });
    const a = deferred();
    s.add({ id: "a", run: () => a.promise });
    s.add({ id: "b", run: () => new Promise(() => {}) });
    s.start();
    a.resolve(1);
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(s.state("b")).toBe("running");
  });
});
