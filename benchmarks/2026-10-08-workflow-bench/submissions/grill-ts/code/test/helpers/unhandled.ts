import { afterEach, beforeEach, expect } from "vitest";
import { flush } from "./fake-clock.js";

/** Fails each test in the calling file if it caused an unhandled promise rejection. */
export function expectNoUnhandledRejections(): void {
  const unhandled: unknown[] = [];
  const record = (reason: unknown) => void unhandled.push(reason);
  beforeEach(() => {
    unhandled.length = 0;
    process.on("unhandledRejection", record);
  });
  afterEach(async () => {
    await flush();
    process.off("unhandledRejection", record);
    expect(unhandled).toEqual([]);
  });
}
