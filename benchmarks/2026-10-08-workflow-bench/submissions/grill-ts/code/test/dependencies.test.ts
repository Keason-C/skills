import { describe, expect, it } from "vitest";
import type { TaskContext } from "../src/index.js";
import { flush } from "./helpers/fake-clock.js";
import { deferred, setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

expectNoUnhandledRejections();

describe("dependencies", () => {
  it("waits for every dependency to succeed and passes their values in ctx.deps", async () => {
    const { s } = setup(3);
    const gateA = deferred();
    let seen: TaskContext | undefined;
    s.add({ id: "a", run: () => gateA.promise });
    s.add({ id: "b", run: async () => "B" });
    s.add({ id: "c", deps: ["a", "b"], run: async (ctx) => void (seen = ctx) });
    s.start();
    await flush();
    expect(s.state("b")).toBe("succeeded");
    expect(s.state("c")).toBe("waiting");
    gateA.resolve("A");
    await flush();
    expect(seen?.deps).toEqual({ a: "A", b: "B" });
    expect(s.state("c")).toBe("succeeded");
  });

  it("accepts forward references and waits until the dependency is added and succeeds", async () => {
    const { s, log } = setup();
    s.add({ id: "late-user", deps: ["late"], run: async (ctx) => ctx.deps.late });
    s.start();
    expect(s.state("late-user")).toBe("waiting");
    s.add({ id: "late", run: async () => "L" });
    await expect(s.result("late-user")).resolves.toBe("L");
    expect(log.filter((e) => e[0] === "start").map((e) => e[1])).toEqual(["late", "late-user"]);
  });

  it("de-duplicates repeated dependency ids", async () => {
    const { s } = setup();
    s.add({ id: "a", run: async () => 1 });
    s.add({ id: "b", deps: ["a", "a"], run: async (ctx) => ctx.deps });
    s.start();
    await expect(s.result("b")).resolves.toEqual({ a: 1 });
  });
});
