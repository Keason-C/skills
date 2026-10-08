import { describe, expect, it } from "vitest";
import { flush } from "./helpers/fake-clock.js";
import { deferred, setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

const startOrder = (log: unknown[][]) => log.filter((e) => e[0] === "start").map((e) => e[1]);

expectNoUnhandledRejections();

describe("priority and ready order", () => {
  it("starts higher priority first, then equal priority in add order", async () => {
    const { s, log } = setup(1);
    s.add({ id: "low", priority: -1, run: async () => 0 });
    s.add({ id: "mid1", run: async () => 0 });
    s.add({ id: "high", priority: 2.5, run: async () => 0 });
    s.add({ id: "mid2", priority: 0, run: async () => 0 });
    s.start();
    await s.onIdle();
    expect(startOrder(log)).toEqual(["high", "mid1", "mid2", "low"]);
  });

  it("orders equal priority by when tasks became ready, not when they were added", async () => {
    const { s, log } = setup(1);
    const gate = deferred();
    s.add({ id: "blocker", run: () => gate.promise });
    s.add({ id: "dep", run: async () => 0 });
    s.add({ id: "early-added", deps: ["dep"], run: async () => 0 });
    s.add({ id: "late-added", run: async () => 0 });
    s.start();
    // blocker runs; dep then late-added are queued; early-added becomes ready only after dep.
    gate.resolve(0);
    await s.onIdle();
    expect(startOrder(log)).toEqual(["blocker", "dep", "late-added", "early-added"]);
  });

  it("starts tasks that became ready at the same moment in add order", async () => {
    const { s, log } = setup(1);
    s.add({ id: "z", deps: ["root"], run: async () => 0 });
    s.add({ id: "root", run: async () => 0 });
    s.add({ id: "a", deps: ["root"], run: async () => 0 });
    s.add({ id: "m", deps: ["root"], run: async () => 0 });
    s.start();
    await s.onIdle();
    expect(startOrder(log)).toEqual(["root", "z", "a", "m"]);
  });

  it("keeps the order correct with many tasks of mixed priorities", async () => {
    const { s, log } = setup(1);
    let seed = 7;
    const rand = () => (seed = (seed * 48271) % 2147483647);
    const specs = Array.from({ length: 300 }, (_, i) => ({ id: `t${i}`, priority: rand() % 7 }));
    for (const { id, priority } of specs) s.add({ id, priority, run: async () => 0 });
    s.start();
    await s.onIdle();
    await flush();
    const expected = specs
      .map((spec, index) => ({ ...spec, index }))
      .sort((x, y) => y.priority - x.priority || x.index - y.index)
      .map((spec) => spec.id);
    expect(startOrder(log)).toEqual(expected);
  });
});
