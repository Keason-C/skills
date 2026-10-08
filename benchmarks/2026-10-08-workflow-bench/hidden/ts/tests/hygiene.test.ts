import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { flush, make } from "./helpers.js";

let unhandled: unknown[] = [];
const onUnhandled = (reason: unknown) => {
  unhandled.push(reason);
};

beforeEach(() => {
  unhandled = [];
  process.on("unhandledRejection", onUnhandled);
});

afterEach(() => {
  process.off("unhandledRejection", onUnhandled);
});

async function expectNoUnhandled(): Promise<void> {
  await flush(40);
  expect(unhandled).toEqual([]);
}

describe("hygiene: unhandled rejections", () => {
  it("a failed task nobody asks the result of causes no unhandled rejection", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.reject("a", new Error("nobody listens"));
    await flush();
    expect(s.state("a")).toBe("failed");
    await expectNoUnhandled();
  });

  it("a synchronously throwing run nobody asks the result of causes no unhandled rejection", async () => {
    const { s } = make(1);
    s.add({
      id: "a",
      run: () => {
        throw new Error("sync");
      },
    });
    s.start();
    await flush();
    expect(s.state("a")).toBe("failed");
    await expectNoUnhandled();
  });

  it("cancelled and cascade-cancelled tasks cause no unhandled rejections", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("q"));
    s.add(runs.task("d", { deps: ["q"] }));
    s.cancel("q");
    s.add(runs.task("late", { deps: ["q"] }));
    s.add(runs.task("w", { deps: ["never-added"] }));
    s.cancel("w");
    expect(s.state("late")).toBe("cancelled");
    await expectNoUnhandled();
  });

  it("a cancelled running task whose run later rejects causes no unhandled rejection", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    s.cancel("a");
    runs.reject("a", new Error("late rejection"));
    await expectNoUnhandled();
  });

  it("a timed-out run that later rejects causes no unhandled rejection", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 10 }));
    s.add(runs.task("b", { deps: ["a"] }));
    s.start();
    await clock.advance(10);
    expect(s.state("a")).toBe("failed");
    runs.reject("a", new Error("late rejection"));
    await expectNoUnhandled();
  });
});

describe("hygiene: timers", () => {
  it("tasks without timeouts or retries create no timers at all", async () => {
    const { s, runs, clock } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.add(runs.task("c", { deps: ["a"] }));
    s.start();
    expect(clock.created).toBe(0);
    runs.resolve("a");
    runs.reject("b");
    await flush();
    runs.resolve("c");
    await flush();
    expect(clock.created).toBe(0);
    expect(clock.pending).toBe(0);
  });

  it("a task that succeeds before its timeout leaves no pending timer", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 1000 }));
    s.start();
    runs.resolve("a");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(clock.pending).toBe(0);
  });

  it("a task that fails before its timeout leaves no pending timer", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 1000 }));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(clock.pending).toBe(0);
  });

  it("a cancelled running task with a timeout leaves no pending timer", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { timeoutMs: 1000 }));
    s.start();
    s.cancel("a");
    await flush();
    expect(clock.pending).toBe(0);
  });

  it("no timers remain after retries, timeouts and an eventual success", async () => {
    const { s, runs, clock } = make(2);
    s.add(runs.task("a", { retries: 3, backoffMs: 20, timeoutMs: 100 }));
    s.add(runs.task("b", { timeoutMs: 100, deps: ["a"] }));
    s.start();
    runs.reject("a"); // attempt 1 fails at t+0
    await flush();
    await clock.advance(20); // attempt 2 starts
    await clock.advance(100); // attempt 2 times out
    await clock.advance(40); // attempt 3 starts
    expect(runs.count("a")).toBe(3);
    runs.resolve("a", "A");
    await flush();
    expect(s.state("b")).toBe("running");
    runs.resolve("b", "B");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(s.state("b")).toBe("succeeded");
    expect(clock.pending).toBe(0);
  });

  it("no timers remain after a final timeout", async () => {
    const { s, runs, clock } = make(1);
    s.add(runs.task("a", { retries: 1, backoffMs: 5, timeoutMs: 10 }));
    s.start();
    await clock.advance(10);
    await clock.advance(5);
    await clock.advance(10);
    expect(s.state("a")).toBe("failed");
    expect(runs.count("a")).toBe(2);
    expect(clock.pending).toBe(0);
  });
});
