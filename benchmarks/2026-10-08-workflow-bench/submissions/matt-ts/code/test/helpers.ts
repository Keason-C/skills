import type { Clock } from "../src/index.js";

interface Timer {
  id: number;
  at: number;
  callback: () => void;
}

/** A manually driven clock. Timers fire only from `advance`. */
export class FakeClock implements Clock {
  private time = 0;
  private nextId = 1;
  private timers = new Map<number, Timer>();

  now(): number {
    return this.time;
  }

  setTimeout(callback: () => void, ms: number): unknown {
    const id = this.nextId++;
    this.timers.set(id, { id, at: this.time + ms, callback });
    return id;
  }

  clearTimeout(handle: unknown): void {
    this.timers.delete(handle as number);
  }

  get pending(): number {
    return this.timers.size;
  }

  /** Advance time, firing due timers in order and flushing microtasks after each. */
  async advance(ms: number): Promise<void> {
    const target = this.time + ms;
    for (;;) {
      await flush();
      let next: Timer | undefined;
      for (const t of this.timers.values()) {
        if (t.at <= target && (!next || t.at < next.at || (t.at === next.at && t.id < next.id))) next = t;
      }
      if (!next) break;
      this.timers.delete(next.id);
      this.time = next.at;
      next.callback();
    }
    this.time = target;
    await flush();
  }
}

/** Let pending promise reactions run. */
export async function flush(): Promise<void> {
  for (let i = 0; i < 20; i++) await Promise.resolve();
}

/** A promise whose settlement the test controls. */
export function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** A task body that never settles. */
export const never = () => new Promise<never>(() => {});
