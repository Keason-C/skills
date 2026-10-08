import { describe, expect, it } from "vitest";
import { Scheduler, TaskError } from "../src/index.js";
import { FakeClock, deferred, flush } from "./helpers.js";

function setup(concurrency = 1) {
  const clock = new FakeClock();
  const s = new Scheduler({ concurrency, clock });
  const log: unknown[][] = [];
  s.on("start", (...a) => log.push(["start", ...a]));
  s.on("retry", (...a) => log.push(["retry", ...a]));
  s.on("success", (...a) => log.push(["success", ...a]));
  s.on("failure", (...a) => log.push(["failure", a[0], a[1].kind]));
  return { clock, s, log };
}

describe("retries and backoff", () => {
  it("retries with exponential backoff on the clock", async () => {
    const { clock, s, log } = setup();
    const errors = [new Error("e1"), new Error("e2"), new Error("e3")];
    s.add({
      id: "a",
      retries: 3,
      backoffMs: 100,
      run: async ({ attempt }) => {
        if (attempt <= 3) throw errors[attempt - 1];
        return "ok";
      },
    });
    s.start();
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(clock.pending).toBe(1);
    await clock.advance(99);
    expect(s.state("a")).toBe("retrying");
    await clock.advance(1);
    expect(s.state("a")).toBe("retrying"); // attempt 2 failed, now waiting 200
    await clock.advance(199);
    expect(log.filter((e) => e[0] === "start")).toHaveLength(2);
    await clock.advance(1 + 400);
    await expect(s.result("a")).resolves.toBe("ok");
    expect(log).toEqual([
      ["start", "a", 1],
      ["retry", "a", 2, 100, errors[0]],
      ["start", "a", 2],
      ["retry", "a", 3, 200, errors[1]],
      ["start", "a", 3],
      ["retry", "a", 4, 400, errors[2]],
      ["start", "a", 4],
      ["success", "a", "ok"],
    ]);
    expect(clock.pending).toBe(0);
  });

  it("fails with kind 'failed' after the last attempt, counting attempts", async () => {
    const { s } = setup();
    const boom = new Error("boom");
    s.add({ id: "a", retries: 2, run: async () => { throw boom; } });
    s.start();
    const err = (await s.result("a").catch((e) => e)) as TaskError;
    expect(err).toBeInstanceOf(TaskError);
    expect(err).toMatchObject({ kind: "failed", attempts: 3, cause: boom, taskId: "a" });
  });

  it("re-queues synchronously after the retry event when the delay is 0", async () => {
    const { clock, s, log } = setup();
    let fail = true;
    s.add({ id: "a", retries: 1, run: async () => { if (fail) { fail = false; throw new Error("x"); } return 1; } });
    s.start();
    await flush();
    expect(clock.pending).toBe(0);
    expect(s.state("a")).toBe("succeeded");
    expect(log.map((e) => e.slice(0, 4))).toEqual([
      ["start", "a", 1],
      ["retry", "a", 2, 0],
      ["start", "a", 2],
      ["success", "a", 1],
    ]);
  });

  it("re-enters the ready order when the backoff ends", async () => {
    const { clock, s, log } = setup();
    const b = deferred();
    let fail = true;
    s.add({ id: "a", retries: 1, backoffMs: 10, priority: 5, run: async () => { if (fail) { fail = false; throw new Error("x"); } } });
    s.add({ id: "b", run: () => b.promise });
    s.add({ id: "c", run: async () => {} });
    s.start();
    await flush(); // a failed, b running, c queued
    await clock.advance(10); // a ready again, but b still holds the slot
    expect(s.state("a")).toBe("queued");
    b.resolve(1);
    await s.onIdle();
    expect(log.filter((e) => e[0] === "start").map((e) => e[1])).toEqual(["a", "b", "a", "c"]);
  });
});

describe("timeouts", () => {
  it("fails a slow attempt, aborts its signal, frees its slot and ignores its late result", async () => {
    const { clock, s, log } = setup();
    let signal: AbortSignal | undefined;
    const slow = deferred();
    s.add({ id: "a", timeoutMs: 50, run: (ctx) => { signal = ctx.signal; return slow.promise; } });
    s.add({ id: "b", run: async () => "b" });
    s.start();
    expect(clock.pending).toBe(1);
    await clock.advance(50);
    expect(s.state("a")).toBe("failed");
    expect(signal?.aborted).toBe(true);
    const reason = signal?.reason as TaskError;
    expect(reason).toBeInstanceOf(TaskError);
    expect(reason).toMatchObject({ kind: "timeout", attempts: 1, taskId: "a" });
    expect(s.state("b")).toBe("succeeded");
    const err = (await s.result("a").catch((e) => e)) as TaskError;
    expect(err).toMatchObject({ kind: "timeout", attempts: 1 });
    slow.resolve("late");
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(log.filter((e) => e[0] === "success").map((e) => e[1])).toEqual(["b"]);
    expect(clock.pending).toBe(0);
  });

  it("retries a timed-out attempt, passing the timeout TaskError to the retry event", async () => {
    const { clock, s, log } = setup();
    const signals: AbortSignal[] = [];
    s.add({
      id: "a",
      timeoutMs: 10,
      retries: 1,
      backoffMs: 5,
      run: (ctx) => {
        signals.push(ctx.signal);
        return ctx.attempt === 1 ? new Promise(() => {}) : Promise.resolve("second");
      },
    });
    s.start();
    await clock.advance(10);
    expect(s.state("a")).toBe("retrying");
    const retry = log.find((e) => e[0] === "retry")!;
    expect(retry.slice(0, 4)).toEqual(["retry", "a", 2, 5]);
    expect(retry[4]).toBe(signals[0]!.reason);
    expect(retry[4]).toMatchObject({ kind: "timeout", attempts: 1 });
    await clock.advance(5);
    await expect(s.result("a")).resolves.toBe("second");
    expect(signals[1]!.aborted).toBe(false);
    expect(clock.pending).toBe(0);
  });

  it("clears the timeout timer when an attempt settles in time", async () => {
    const { clock, s } = setup();
    s.add({ id: "a", timeoutMs: 1000, run: async () => 1 });
    s.start();
    expect(clock.pending).toBe(1);
    await s.result("a");
    expect(clock.pending).toBe(0);
  });
});
