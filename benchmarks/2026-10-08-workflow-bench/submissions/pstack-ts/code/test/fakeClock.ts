import type { Clock } from "../src/index.js";

interface Timer {
  readonly handle: number;
  readonly due: number;
  readonly callback: () => void;
}

export async function flushMicrotasks(rounds = 50): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await Promise.resolve();
  }
}

export class FakeClock implements Clock {
  private time: number;
  private seq = 0;
  private readonly timers = new Map<number, Timer>();
  setTimeoutCalls = 0;
  clearTimeoutCalls = 0;

  constructor(start = 0) {
    this.time = start;
  }

  now(): number {
    return this.time;
  }

  setTimeout(callback: () => void, ms: number): unknown {
    if (typeof callback !== "function") {
      throw new TypeError("FakeClock.setTimeout: callback is not a function");
    }
    if (!Number.isFinite(ms) || ms < 0) {
      throw new RangeError(`FakeClock.setTimeout: invalid delay ${String(ms)}`);
    }
    this.setTimeoutCalls++;
    const handle = ++this.seq;
    this.timers.set(handle, { handle, due: this.time + ms, callback });
    return handle;
  }

  clearTimeout(handle: unknown): void {
    this.clearTimeoutCalls++;
    if (typeof handle === "number") {
      this.timers.delete(handle);
    }
  }

  pendingCount(): number {
    return this.timers.size;
  }

  pending(): number[] {
    return this.sorted().map((t) => t.due);
  }

  fireNextSync(): boolean {
    const next = this.sorted()[0];
    if (!next) return false;
    this.timers.delete(next.handle);
    this.time = Math.max(this.time, next.due);
    next.callback();
    return true;
  }

  async advance(ms: number): Promise<void> {
    if (!Number.isFinite(ms) || ms < 0) {
      throw new RangeError(`FakeClock.advance: invalid delta ${String(ms)}`);
    }
    const target = this.time + ms;
    await flushMicrotasks();
    for (;;) {
      const next = this.sorted()[0];
      if (!next || next.due > target) break;
      this.fireNextSync();
      await flushMicrotasks();
    }
    this.time = target;
  }

  flush(): Promise<void> {
    return flushMicrotasks();
  }

  private sorted(): Timer[] {
    return [...this.timers.values()].sort((a, b) => a.due - b.due || a.handle - b.handle);
  }
}
