import { describe, expect, it } from "vitest";
import { flush } from "./helpers/fake-clock.js";
import { deferred, setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

const boom = new Error("boom");

expectNoUnhandledRejections();

describe("retries and backoff", () => {
  it("retries with exponential backoff on the clock, then succeeds", async () => {
    const { s, clock, log } = setup();
    let attempt = 0;
    s.add({
      id: "a",
      retries: 3,
      backoffMs: 100,
      run: async (ctx) => {
        attempt = ctx.attempt;
        if (ctx.attempt < 3) throw boom;
        return "ok";
      },
    });
    s.start();
    await flush();
    expect(s.state("a")).toBe("retrying");
    expect(clock.pendingCount()).toBe(1);
    await clock.advance(99);
    expect(attempt).toBe(1);
    await clock.advance(1);
    expect(attempt).toBe(2);
    await clock.advance(199);
    expect(s.state("a")).toBe("retrying");
    await clock.advance(1);
    await expect(s.result("a")).resolves.toBe("ok");
    expect(log).toEqual([
      ["start", "a", 1],
      ["retry", "a", 2, 100, boom],
      ["start", "a", 2],
      ["retry", "a", 3, 200, boom],
      ["start", "a", 3],
      ["success", "a", "ok"],
      ["idle"],
    ]);
    expect(clock.pendingCount()).toBe(0);
  });

  it("fails with the final attempt's error once retries are exhausted", async () => {
    const { s, clock } = setup();
    const errors = [new Error("1"), new Error("2")];
    s.add({ id: "a", retries: 1, backoffMs: 10, run: async (ctx) => Promise.reject(errors[ctx.attempt - 1]) });
    s.start();
    await clock.advance(10);
    expect(s.state("a")).toBe("failed");
    await expect(s.result("a")).rejects.toMatchObject({ kind: "failed", attempts: 2, cause: errors[1] });
    expect(clock.pendingCount()).toBe(0);
  });

  it("retries a zero delay without a timer; the retry listener sees retrying, then it re-queues", async () => {
    const { s, clock, log } = setup();
    const seenInRetry: string[] = [];
    s.on("retry", (id) => void seenInRetry.push(s.state(id)));
    s.add({
      id: "a",
      retries: 2,
      run: async (ctx) => {
        if (ctx.attempt < 3) throw boom;
        return ctx.attempt;
      },
    });
    s.start();
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(seenInRetry).toEqual(["retrying", "retrying"]);
    expect(log.map((e) => e.slice(0, 4))).toEqual([
      ["start", "a", 1],
      ["retry", "a", 2, 0],
      ["start", "a", 2],
      ["retry", "a", 3, 0],
      ["start", "a", 3],
      ["success", "a", 3],
      ["idle"],
    ]);
    expect(clock.pendingCount()).toBe(0);
  });

  it("re-enters the ready order when the backoff ends, behind tasks already queued", async () => {
    const { s, clock, log } = setup(1);
    const gate = deferred();
    s.add({ id: "flaky", retries: 1, backoffMs: 5, run: async (ctx) => (ctx.attempt === 1 ? Promise.reject(boom) : 0) });
    s.add({ id: "long", run: () => gate.promise });
    s.add({ id: "queued-early", run: async () => 0 });
    s.start();
    await clock.advance(5); // flaky ready again while long runs; queued-early is ahead of it
    gate.resolve(0);
    await s.onIdle();
    expect(log.filter((e) => e[0] === "start").map((e) => e.slice(1))).toEqual([
      ["flaky", 1],
      ["long", 1],
      ["queued-early", 1],
      ["flaky", 2],
    ]);
  });

  it("lets a backoff end while paused, leaving the task queued until start()", async () => {
    const { s, clock } = setup();
    s.add({ id: "a", retries: 1, backoffMs: 10, run: async (ctx) => (ctx.attempt === 1 ? Promise.reject(boom) : 0) });
    s.start();
    await flush();
    s.pause();
    await clock.advance(10);
    expect(s.state("a")).toBe("queued");
    s.start();
    expect(s.state("a")).toBe("running");
  });
});
