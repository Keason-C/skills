import { describe, expect, it } from "vitest";
import { flush, make } from "./helpers.js";

describe("ordering, concurrency and synchronous dispatch", () => {
  it("start() fills up to `concurrency` slots in add order; the rest stay queued", () => {
    const { s, runs } = make(2);
    for (const id of ["a", "b", "c", "d"]) s.add(runs.task(id));
    s.start();
    expect(runs.order).toEqual(["a", "b"]);
    expect(s.state("a")).toBe("running");
    expect(s.state("b")).toBe("running");
    expect(s.state("c")).toBe("queued");
    expect(s.state("d")).toBe("queued");
  });

  it("run is invoked synchronously inside start()", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    expect(runs.calls.length).toBe(0);
    s.start();
    expect(runs.order).toEqual(["a"]);
  });

  it("a finished task's slot goes to the next ready task", async () => {
    const { s, runs } = make(2);
    for (const id of ["a", "b", "c", "d"]) s.add(runs.task(id));
    s.start();
    runs.resolve("b", 1);
    await flush();
    expect(runs.order).toEqual(["a", "b", "c"]);
    expect(s.state("d")).toBe("queued");
    runs.reject("a");
    await flush();
    expect(runs.order).toEqual(["a", "b", "c", "d"]);
  });

  it("add() on a started scheduler with a free slot invokes run before add returns", () => {
    const { s, runs } = make(2);
    s.start();
    s.add(runs.task("a"));
    expect(runs.order).toEqual(["a"]);
    expect(s.state("a")).toBe("running");
  });

  it("add() on a started scheduler with no free slot leaves the task queued", () => {
    const { s, runs } = make(1);
    s.start();
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    expect(runs.order).toEqual(["a"]);
    expect(s.state("b")).toBe("queued");
  });

  it("cancel() of a running task starts the next queued task before cancel returns", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    s.cancel("a");
    expect(runs.order).toEqual(["a", "b"]);
    expect(s.state("b")).toBe("running");
  });

  it("a backoff timer callback dispatches the retried task synchronously", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 100 }));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(clock.runNext()).toBe(true);
    // no await: run must already have been invoked by the timer callback
    expect(runs.count("a")).toBe(2);
    expect(s.state("a")).toBe("running");
  });

  it("higher priority starts first", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("low", { priority: 0 }));
    s.add(runs.task("high", { priority: 5 }));
    s.add(runs.task("mid", { priority: 1 }));
    s.start();
    expect(runs.order).toEqual(["high"]);
    runs.resolve("high");
    await flush();
    expect(runs.order).toEqual(["high", "mid"]);
    runs.resolve("mid");
    await flush();
    expect(runs.order).toEqual(["high", "mid", "low"]);
  });

  it("negative and fractional priorities are ordered numerically (default 0)", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("n", { priority: -1 }));
    s.add(runs.task("f", { priority: 0.5 }));
    s.add(runs.task("z"));
    s.add(runs.task("q", { priority: 0.25 }));
    s.start();
    for (let i = 0; i < 3; i++) {
      runs.resolve(runs.order[runs.order.length - 1]!);
      await flush();
    }
    expect(runs.order).toEqual(["f", "q", "z", "n"]);
  });

  it("equal priority: tasks start in the order they became ready, not the order they were added", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("d"));
    s.add(runs.task("blk"));
    s.start();
    s.add(runs.task("x", { deps: ["d"] })); // added first, ready later
    s.add(runs.task("y")); // added second, ready now
    expect(s.state("x")).toBe("waiting");
    expect(s.state("y")).toBe("queued");
    runs.resolve("d");
    await flush();
    expect(s.state("y")).toBe("running");
    expect(s.state("x")).toBe("queued");
    runs.resolve("y");
    await flush();
    expect(s.state("x")).toBe("running");
    expect(runs.order).toEqual(["d", "blk", "y", "x"]);
  });

  it("tasks that became ready at the same moment start in the order they were added", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("z", { deps: ["a"] }));
    s.add(runs.task("m", { deps: ["a"] }));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    runs.resolve("a");
    await flush();
    runs.resolve("z");
    await flush();
    runs.resolve("m");
    await flush();
    expect(runs.order).toEqual(["a", "z", "m", "b"]);
  });

  it("priority beats readiness order", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("y")); // ready early, priority 0
    s.add(runs.task("x", { deps: ["a"], priority: 3 })); // ready later, priority 3
    s.start();
    runs.resolve("a");
    await flush();
    expect(s.state("x")).toBe("running");
    expect(s.state("y")).toBe("queued");
    runs.resolve("x");
    await flush();
    expect(runs.order).toEqual(["a", "x", "y"]);
  });

  it("among tasks that become ready at the same moment, priority beats add order", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("lo", { deps: ["a"], priority: 0 }));
    s.add(runs.task("hi", { deps: ["a"], priority: 1 }));
    s.start();
    runs.resolve("a");
    await flush();
    runs.resolve("hi");
    await flush();
    expect(runs.order).toEqual(["a", "hi", "lo"]);
  });

  it("a newly added higher-priority task goes ahead of already queued lower-priority tasks", async () => {
    const { s, runs } = make(1);
    s.start();
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.add(runs.task("c", { priority: 2 }));
    runs.resolve("a");
    await flush();
    runs.resolve("c");
    await flush();
    expect(runs.order).toEqual(["a", "c", "b"]);
  });

  it("running tasks never exceed concurrency and slots are always used when work is ready", async () => {
    const { s, runs } = make(3);
    const ids = ["t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7"];
    for (const id of ids) s.add(runs.task(id));
    const running = () => ids.filter((id) => s.state(id) === "running");
    const unfinished = () =>
      ids.filter((id) => ["queued", "running"].includes(s.state(id))).length;
    s.start();
    expect(running()).toEqual(["t0", "t1", "t2"]);
    const steps: string[][] = [["t1"], ["t0", "t3"], ["t2"], ["t5", "t4", "t6"], ["t7"]];
    for (const step of steps) {
      for (const id of step) runs.resolve(id);
      await flush();
      expect(running().length).toBe(Math.min(3, unfinished()));
    }
    expect(runs.order).toEqual(ids);
    expect(ids.every((id) => s.state(id) === "succeeded")).toBe(true);
  });
});
