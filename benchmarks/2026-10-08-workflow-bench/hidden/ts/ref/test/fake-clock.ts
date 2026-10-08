import type { Clock } from "../src/index.js";

interface Timer {
  id: number;
  due: number;
  callback: () => void;
}

/** Deterministic clock: timers only fire through advance(). */
export class FakeClock implements Clock {
  #now = 0;
  #nextId = 1;
  #timers = new Map<number, Timer>();

  now(): number {
    return this.#now;
  }

  setTimeout(callback: () => void, ms: number): unknown {
    const id = this.#nextId++;
    this.#timers.set(id, { id, due: this.#now + Math.max(0, ms), callback });
    return id;
  }

  clearTimeout(handle: unknown): void {
    this.#timers.delete(handle as number);
  }

  /** Number of timers created and not yet fired or cleared. */
  get pending(): number {
    return this.#timers.size;
  }

  /** Advances time by `ms`, firing due timers in (due, creation) order, flushing microtasks after each. */
  async advance(ms: number): Promise<void> {
    const target = this.#now + ms;
    for (;;) {
      let next: Timer | undefined;
      for (const t of this.#timers.values()) {
        if (t.due <= target && (!next || t.due < next.due || (t.due === next.due && t.id < next.id))) next = t;
      }
      if (!next) break;
      this.#timers.delete(next.id);
      this.#now = next.due;
      next.callback();
      await flush();
    }
    this.#now = target;
    await flush();
  }
}

/** Lets all pending promise reactions run (uses a real macrotask; test-only). */
export function flush(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}

/** A promise whose settlement the test controls. */
export function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
