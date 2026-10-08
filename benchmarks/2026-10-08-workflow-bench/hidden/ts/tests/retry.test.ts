import { describe, expect, it } from "vitest";
import type { TaskContext } from "../src/index.js";
import { errInfo, evs, flush, make, track } from "./helpers.js";

// Every test here uses backoffMs > 0 (backoff 0 behaviour is a product-owner decision, see po.test.ts).
describe("retries and backoff", () => {
  it("a failed attempt with retries left becomes retrying and waits backoffMs before attempt 2", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 2, backoffMs: 100 }));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    await clock.advance(99);
    expect(s.state("a")).toBe("retrying");
    expect(runs.count("a")).toBe(1);
    await clock.advance(1);
    expect(runs.count("a")).toBe(2);
    expect(runs.last("a").attempt).toBe(2);
    expect(runs.last("a").ctx.attempt).toBe(2);
    expect(s.state("a")).toBe("running");
  });

  it("the backoff doubles: backoffMs * 2^(n-1) before attempt n+1", async () => {
    const { s, runs, clock } = make(1);
    const times: number[] = [];
    const inner = runs.fn("a");
    s.add({
      id: "a",
      retries: 3,
      backoffMs: 50,
      run: (ctx: TaskContext) => {
        times.push(clock.now());
        return inner(ctx);
      },
    });
    s.start();
    for (const delay of [50, 100, 200]) {
      const before = runs.count("a");
      runs.reject("a");
      await flush();
      await clock.advance(delay - 1);
      expect(runs.count("a")).toBe(before);
      await clock.advance(1);
      expect(runs.count("a")).toBe(before + 1);
    }
    expect(times.map((t) => t - times[0]!)).toEqual([0, 50, 150, 350]);
    expect(runs.callsOf("a").map((c) => c.attempt)).toEqual([1, 2, 3, 4]);
  });

  it("retry events carry nextAttempt and the delay, emitted when the attempt fails", async () => {
    const { s, runs, clock, events } = make(1, { events: true });
    s.add(runs.task("a", { retries: 2, backoffMs: 30 }));
    s.start();
    runs.reject("a");
    await flush();
    expect(events!.raw.filter((e) => e.event === "retry").map((e) => e.args.slice(0, 3))).toEqual([
      ["a", 2, 30],
    ]);
    await clock.advance(30);
    runs.reject("a");
    await flush();
    expect(events!.raw.filter((e) => e.event === "retry").map((e) => e.args.slice(0, 3))).toEqual([
      ["a", 2, 30],
      ["a", 3, 60],
    ]);
  });

  it("a task that succeeds on a retry ends succeeded with that value and emits no failure", async () => {
    const { s, runs, clock, log } = make(1, { events: true });
    s.add(runs.task("a", { retries: 2, backoffMs: 10 }));
    const r = track(s.result("a"));
    s.start();
    runs.reject("a");
    await flush();
    await clock.advance(10);
    runs.resolve("a", "second time lucky");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(r.value).toBe("second time lucky");
    expect(evs(log)).toEqual(["start:a:1", "retry:a:2:10", "start:a:2", "success:a", "idle"]);
  });

  it("exhausting the retries ends failed with attempts = retries + 1", async () => {
    const { s, runs, clock, log } = make(1, { events: true });
    s.add(runs.task("a", { retries: 2, backoffMs: 10 }));
    const r = track(s.result("a"));
    s.start();
    runs.reject("a");
    await flush();
    await clock.advance(10);
    runs.reject("a");
    await flush();
    await clock.advance(20);
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(runs.count("a")).toBe(3);
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "failed", attempts: 3 });
    expect(evs(log).filter((l) => l.startsWith("failure"))).toEqual(["failure:a"]);
    await clock.advance(10_000);
    expect(runs.count("a")).toBe(3);
  });

  it("a retried task re-enters the ready order when its backoff ends (behind tasks ready earlier)", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 10 }));
    s.add(runs.task("b"));
    s.add(runs.task("c"));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(s.state("b")).toBe("running");
    await clock.advance(10);
    expect(s.state("a")).toBe("queued");
    runs.resolve("b");
    await flush();
    expect(s.state("c")).toBe("running");
    expect(s.state("a")).toBe("queued");
    runs.resolve("c");
    await flush();
    expect(s.state("a")).toBe("running");
    expect(runs.order).toEqual(["a", "b", "c", "a"]);
  });

  it("a retried task with higher priority goes ahead of tasks that were ready earlier", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 10, priority: 1 }));
    s.add(runs.task("b"));
    s.add(runs.task("c"));
    s.start();
    runs.reject("a");
    await flush();
    await clock.advance(10);
    runs.resolve("b");
    await flush();
    expect(runs.order).toEqual(["a", "b", "a"]);
    expect(s.state("c")).toBe("queued");
  });

  it("a backoff that ends while paused leaves the task queued until start()", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 10 }));
    s.start();
    runs.reject("a");
    await flush();
    s.pause();
    await clock.advance(10);
    expect(s.state("a")).toBe("queued");
    expect(runs.count("a")).toBe(1);
    s.start();
    expect(runs.count("a")).toBe(2);
    expect(s.state("a")).toBe("running");
  });

  it("a synchronously throwing attempt is retried like a rejected one", async () => {
    const { s, clock } = make(1);
    const seen: number[] = [];
    s.add({
      id: "t",
      retries: 1,
      backoffMs: 5,
      run: (ctx) => {
        seen.push(ctx.attempt);
        if (ctx.attempt === 1) throw new Error("sync");
        return Promise.resolve("ok");
      },
    });
    const r = track(s.result("t"));
    s.start();
    await flush();
    expect(s.state("t")).toBe("retrying");
    await clock.advance(5);
    await flush();
    expect(seen).toEqual([1, 2]);
    expect(s.state("t")).toBe("succeeded");
    expect(r.value).toBe("ok");
  });

  it("each retry attempt receives the same ctx.deps", async () => {
    const { s, runs, clock } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b", { deps: ["a"], retries: 1, backoffMs: 10 }));
    s.start();
    runs.resolve("a", "A");
    await flush();
    runs.reject("b");
    await flush();
    await clock.advance(10);
    expect(runs.callsOf("b").map((c) => c.ctx.deps)).toEqual([{ a: "A" }, { a: "A" }]);
  });
});
