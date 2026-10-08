import { describe, expect, test } from "vitest";
import { Scheduler, systemClock } from "../src/index.js";
import { FakeClock } from "./fakeClock.js";
import { instant, scripted, setup } from "./harness.js";

describe("constructor", () => {
  test.each([0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "concurrency %s throws RangeError",
    (concurrency) => {
      expect(() => new Scheduler({ concurrency, clock: new FakeClock() })).toThrow(RangeError);
    },
  );

  test.each([1, 2, 1000])("concurrency %s is accepted", (concurrency) => {
    const s = new Scheduler({ concurrency, clock: new FakeClock() });
    expect(() => s.state("nope")).toThrow(Error);
  });

  test("a new scheduler is paused: added tasks stay queued until start()", async () => {
    const { s, take, flush } = setup();
    const a = instant(s, "A");
    expect(s.state("A")).toBe("queued");
    await flush();
    expect(a.calls).toHaveLength(0);
    expect(s.state("A")).toBe("queued");
    expect(take()).toEqual([]);
  });

  test("no idle event on construction", async () => {
    const { take, flush } = setup();
    await flush();
    expect(take()).toEqual([]);
  });

  test("uses the injected clock for timers and time", async () => {
    const { s, clock, flush } = setup();
    scripted(s, { id: "A", retries: 1, backoffMs: 40 }, [{ reject: new Error("x") }, { ok: 1 }]);
    s.start();
    await flush();
    expect(clock.pending()).toEqual([40]);
    expect(s.state("A")).toBe("retrying");
    await clock.advance(40);
    expect(s.state("A")).toBe("succeeded");
    expect(clock.pendingCount()).toBe(0);
  });

  test("systemClock delegates to Date.now and global timers", () => {
    const before = Date.now();
    const now = systemClock.now();
    expect(now).toBeGreaterThanOrEqual(before);
    expect(now).toBeLessThanOrEqual(Date.now());
    const handle = systemClock.setTimeout(() => {
      throw new Error("cleared timer must not fire");
    }, 0);
    expect(handle).toBeDefined();
    expect(() => systemClock.clearTimeout(handle)).not.toThrow();
  });
});
