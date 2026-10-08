import { describe, expect, it } from "vitest";
import { flush } from "./helpers/fake-clock.js";
import { setup } from "./helpers/setup.js";
import { expectNoUnhandledRejections } from "./helpers/unhandled.js";

expectNoUnhandledRejections();

describe("events", () => {
  it("emits start before run is invoked, then success with the value", async () => {
    const { s, log } = setup();
    s.add({
      id: "a",
      run: async () => {
        log.push(["run a"]);
        return "v";
      },
    });
    s.start();
    await flush();
    expect(log).toEqual([["start", "a", 1], ["run a"], ["success", "a", "v"], ["idle"]]);
  });

  it("calls a listener once per registration; each unsubscribe removes only its own, and twice is harmless", async () => {
    const { s } = setup();
    const seen: string[] = [];
    const listener = (id: string) => void seen.push(id);
    const off1 = s.on("start", listener);
    s.on("start", listener);
    s.add({ id: "a", run: async () => 1 });
    s.start();
    expect(seen).toEqual(["a", "a"]);
    off1();
    off1();
    s.add({ id: "b", run: async () => 1 });
    await flush();
    expect(seen).toEqual(["a", "a", "b"]);
  });

  it("emits from a snapshot: listeners added during an emit miss it, removed ones still get it", () => {
    const { s } = setup();
    const seen: string[] = [];
    let offLate = () => {};
    s.on("start", () => {
      seen.push("first");
      s.on("start", () => void seen.push("added-late"));
      offLate();
    });
    offLate = s.on("start", () => void seen.push("removed-during"));
    s.add({ id: "a", run: async () => 1 });
    s.start();
    expect(seen).toEqual(["first", "removed-during"]);
  });

  it("swallows listener exceptions and keeps notifying and scheduling", async () => {
    const { s, log } = setup();
    s.on("success", () => {
      throw new Error("listener bug");
    });
    s.add({ id: "a", run: async () => 1 });
    s.add({ id: "b", run: async () => 2 });
    s.start();
    await flush();
    expect(log).toEqual([
      ["start", "a", 1],
      ["success", "a", 1],
      ["start", "b", 1],
      ["success", "b", 2],
      ["idle"],
    ]);
  });

  it("throws for an unknown event name", () => {
    const { s } = setup();
    expect(() => s.on("nope" as "start", () => {})).toThrow(Error);
  });
});
