import type { Clock } from "../../src/index.js";

interface Timer {
  due: number;
  seq: number;
  callback: () => void;
}

/** Lets every pending microtask (and promise chain) run to completion. */
export function flush(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}

/**
 * A manual clock. Timers fire only from `advance`, in due-time order (then creation order), with
 * microtasks flushed before and after each one.
 */
export class FakeClock implements Clock {
  private time = 0;
  private nextSeq = 1;
  private readonly timers = new Map<number, Timer>();

  now(): number {
    return this.time;
  }

  setTimeout(callback: () => void, ms: number): unknown {
    const seq = this.nextSeq++;
    this.timers.set(seq, { due: this.time + Math.max(0, ms), seq, callback });
    return seq;
  }

  clearTimeout(handle: unknown): void {
    this.timers.delete(handle as number);
  }

  pendingCount(): number {
    return this.timers.size;
  }

  async advance(ms: number): Promise<void> {
    const target = this.time + ms;
    await flush();
    for (;;) {
      const next = this.nextDue(target);
      if (!next) break;
      this.timers.delete(next.seq);
      this.time = next.due;
      next.callback();
      await flush();
    }
    this.time = target;
  }

  private nextDue(limit: number): Timer | undefined {
    let best: Timer | undefined;
    for (const t of this.timers.values()) {
      if (t.due > limit) continue;
      if (!best || t.due < best.due || (t.due === best.due && t.seq < best.seq)) best = t;
    }
    return best;
  }
}
