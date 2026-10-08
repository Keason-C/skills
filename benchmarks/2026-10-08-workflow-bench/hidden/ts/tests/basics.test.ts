import { describe, expect, it } from "vitest";
import { TaskError } from "../src/index.js";
import { errInfo, flush, make, track } from "./helpers.js";

describe("basics", () => {
  it("a new scheduler is paused: added tasks are queued and do not run", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    expect(s.state("a")).toBe("queued");
    await flush();
    expect(runs.calls.length).toBe(0);
    expect(s.state("a")).toBe("queued");
  });

  it("start() runs a ready task: state running, attempt 1", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.start();
    expect(runs.count("a")).toBe(1);
    expect(runs.last("a").attempt).toBe(1);
    expect(s.state("a")).toBe("running");
  });

  it("ctx.signal is a non-aborted AbortSignal and ctx.attempt is 1", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    const ctx = runs.last("a").ctx;
    expect(ctx.signal).toBeInstanceOf(AbortSignal);
    expect(ctx.signal.aborted).toBe(false);
    expect(ctx.attempt).toBe(1);
  });

  it("a task that resolves ends succeeded and result() resolves with its value (by identity)", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    const r = track(s.result("a"));
    s.start();
    await flush();
    expect(r.settled).toBe(false);
    const value = { answer: 42 };
    runs.resolve("a", value);
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(r.status).toBe("fulfilled");
    expect(r.value).toBe(value);
  });

  it("result() called after the task succeeded still resolves with the value", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.resolve("a", "done");
    await flush();
    expect(s.state("a")).toBe("succeeded");
    await expect(s.result("a")).resolves.toBe("done");
  });

  it("resolving with undefined is a success", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.resolve("a", undefined);
    await flush();
    expect(s.state("a")).toBe("succeeded");
    await expect(s.result("a")).resolves.toBeUndefined();
  });

  it("a task that rejects (retries 0) ends failed; result() rejects with a TaskError of kind failed", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    const r = track(s.result("a"));
    s.start();
    runs.reject("a", new Error("boom"));
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(r.status).toBe("rejected");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "failed", attempts: 1 });
    expect(runs.count("a")).toBe(1);
  });

  it("a run that throws synchronously is treated like a rejection", async () => {
    const { s, runs } = make(1);
    let calls = 0;
    s.add({
      id: "a",
      run: () => {
        calls++;
        throw new Error("sync boom");
      },
    });
    s.add(runs.task("b"));
    const r = track(s.result("a"));
    expect(() => s.start()).not.toThrow();
    await flush();
    expect(calls).toBe(1);
    expect(s.state("a")).toBe("failed");
    expect(errInfo(r.error)).toEqual({ taskId: "a", kind: "failed", attempts: 1 });
    // the scheduler keeps going: the freed slot is used by the next task
    expect(s.state("b")).toBe("running");
  });

  it("ctx.deps maps each dependency id to its result value", async () => {
    const { s, runs } = make(3);
    const yv = { y: true };
    s.add(runs.task("x"));
    s.add(runs.task("y"));
    s.add(runs.task("z", { deps: ["x", "y"] }));
    s.start();
    runs.resolve("x", 1);
    runs.resolve("y", yv);
    await flush();
    expect(s.state("z")).toBe("running");
    const deps = runs.last("z").ctx.deps;
    expect(deps).toEqual({ x: 1, y: yv });
    expect(deps["y"]).toBe(yv);
  });

  it("ctx.deps is an empty object for a task without dependencies", () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    expect(runs.last("a").ctx.deps).toEqual({});
  });

  it("pause() lets running tasks finish but starts no new ones; start() resumes", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    s.start();
    expect(s.state("a")).toBe("running");
    s.pause();
    expect(s.state("a")).toBe("running");
    runs.resolve("a", 1);
    await flush();
    expect(s.state("a")).toBe("succeeded");
    expect(s.state("b")).toBe("queued");
    expect(runs.count("b")).toBe(0);
    s.start();
    expect(runs.count("b")).toBe(1);
    expect(s.state("b")).toBe("running");
  });

  it("tasks added while paused stay queued until start()", async () => {
    const { s, runs } = make(2);
    s.start();
    s.pause();
    s.add(runs.task("a"));
    await flush();
    expect(s.state("a")).toBe("queued");
    expect(runs.count("a")).toBe(0);
    s.start();
    expect(s.state("a")).toBe("running");
  });

  it("one task failing does not affect an independent task", async () => {
    const { s, runs } = make(2);
    s.add(runs.task("a"));
    s.add(runs.task("b"));
    const rb = track(s.result("b"));
    s.start();
    runs.reject("a");
    await flush();
    expect(s.state("a")).toBe("failed");
    expect(s.state("b")).toBe("running");
    runs.resolve("b", "ok");
    await flush();
    expect(s.state("b")).toBe("succeeded");
    expect(rb.value).toBe("ok");
  });

  it("the rejection error is a TaskError instance", async () => {
    const { s, runs } = make(1);
    s.add(runs.task("a"));
    s.start();
    runs.reject("a");
    await flush();
    await expect(s.result("a")).rejects.toBeInstanceOf(TaskError);
  });
});
