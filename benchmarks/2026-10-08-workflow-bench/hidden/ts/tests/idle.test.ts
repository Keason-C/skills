import { describe, expect, it } from "vitest";
import { flush, make, track } from "./helpers.js";

describe("idle", () => {
  it("onIdle() resolves only once every task has finished", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    const p = track(s.onIdle());
    await flush();
    expect(p.settled).toBe(false);
    runs.resolve("a");
    await flush();
    expect(p.settled).toBe(false);
    runs.resolve("b");
    await flush();
    expect(p.status).toBe("fulfilled");
    expect(p.value).toBeUndefined();
  });

  it("onIdle() stays pending while a dependent still has to run", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    const p = track(s.onIdle());
    runs.resolve("a");
    await flush();
    expect(s.state("b")).toBe("running");
    expect(p.settled).toBe(false);
    runs.resolve("b");
    await flush();
    expect(p.status).toBe("fulfilled");
  });

  it("onIdle() stays pending while a task is retrying", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 100 }));
    s.start();
    const p = track(s.onIdle());
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(p.settled).toBe(false);
    await clock.advance(100);
    expect(p.settled).toBe(false);
    runs.resolve("a");
    await flush();
    expect(p.status).toBe("fulfilled");
  });

  it("onIdle() resolves after a failure and its cascade finish everything", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    const p = track(s.onIdle());
    runs.reject("a");
    await flush();
    expect(p.status).toBe("fulfilled");
  });

  it("onIdle() resolves after the last running task is cancelled", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    const p = track(s.onIdle());
    s.cancel("a");
    await flush();
    expect(p.status).toBe("fulfilled");
  });

  it("onIdle() on a scheduler whose tasks have all finished resolves (in a microtask)", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.resolve("a");
    await flush();
    const p1 = track(s.onIdle());
    const p2 = track(s.onIdle());
    await flush();
    expect(p1.status).toBe("fulfilled");
    expect(p2.status).toBe("fulfilled");
  });

  it("the idle event fires once per busy-to-idle transition", async () => {
    const { s, runs, log } = make(1, { events: true });
    s.add(runs.task("a"));
    s.start();
    runs.resolve("a");
    await flush();
    expect(log.filter((l) => l === "idle").length).toBe(1);
    s.add(runs.task("b"));
    const p = track(s.onIdle());
    await flush();
    expect(p.settled).toBe(false);
    expect(log.filter((l) => l === "idle").length).toBe(1);
    runs.resolve("b");
    await flush();
    expect(p.status).toBe("fulfilled");
    expect(log.filter((l) => l === "idle").length).toBe(2);
  });

  it("every pending onIdle() promise resolves at the same transition", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    const ps = [track(s.onIdle()), track(s.onIdle()), track(s.onIdle())];
    runs.resolve("a");
    await flush();
    expect(ps.map((p) => p.status)).toEqual(["fulfilled", "fulfilled", "fulfilled"]);
  });
});
