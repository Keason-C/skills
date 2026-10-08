import { describe, expect, it } from "vitest";
import { Scheduler } from "../src/index.js";
import { FakeClock, flush, make } from "./helpers.js";

describe("validation", () => {
  it.each([0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY])(
    "concurrency %s is rejected with a RangeError",
    (concurrency) => {
      expect(() => new Scheduler({ concurrency, clock: new FakeClock() })).toThrow(RangeError);
    },
  );

  it("concurrency 1 and 4 are accepted", () => {
    expect(() => new Scheduler({ concurrency: 1, clock: new FakeClock() })).not.toThrow();
    expect(() => new Scheduler({ concurrency: 4, clock: new FakeClock() })).not.toThrow();
  });

  it("the clock option is optional", () => {
    const s = new Scheduler({ concurrency: 1 });
    s.add({ id: "a", run: async () => 1 });
    expect(s.state("a")).toBe("queued");
  });

  it("adding a duplicate id throws an Error and does not replace the original", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    let dupRan = false;
    expect(() =>
      s.add({
        id: "a",
        run: async () => {
          dupRan = true;
          return "dup";
        },
      }),
    ).toThrow(Error);
    s.start();
    runs.resolve("a", "original");
    await flush();
    expect(dupRan).toBe(false);
    await expect(s.result("a")).resolves.toBe("original");
  });

  it("ids stay unique for the scheduler's lifetime (finished tasks included)", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("done"));
    s.add(runs.task("gone"));
    s.cancel("gone");
    s.start();
    runs.resolve("done");
    await flush();
    expect(() => s.add(runs.task("done"))).toThrow(Error);
    expect(() => s.add(runs.task("gone"))).toThrow(Error);
    expect(s.state("done")).toBe("succeeded");
    expect(s.state("gone")).toBe("cancelled");
  });

  it("state() of an unknown id throws an Error", () => {
    const { s } = make(1);
    expect(() => s.state("nope")).toThrow(Error);
  });

  it("explicit defaults as in the brief's example are accepted", async () => {
    const { s, runs } = make(1);
    s.add({ ...runs.task("a"), deps: [], priority: 0, retries: 0, backoffMs: 0, timeoutMs: undefined });
    s.start();
    expect(s.state("a")).toBe("running");
    runs.resolve("a", 1);
    await flush();
    expect(s.state("a")).toBe("succeeded");
  });

  it("negative and fractional priorities are accepted", () => {
    const { s, runs } = make(1);
    expect(() => s.add(runs.task("a", { priority: -3.75 }))).not.toThrow();
    expect(() => s.add(runs.task("b", { priority: 0.001 }))).not.toThrow();
    expect(s.state("a")).toBe("queued");
  });
});
