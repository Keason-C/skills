// Small helpers for the scheduler. Kept free of imports from index.ts to avoid a module cycle.

export interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

/** A deferred whose rejection is never reported as unhandled. */
export function quietDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  promise.catch(() => {});
  return { promise, resolve, reject };
}

/**
 * Finds a dependency cycle that adding `id` with `deps` would close, following "depends on"
 * edges through `depsOf` (undefined for ids not added yet). Returns the ids on the cycle,
 * starting at `id`, or null if there is none.
 */
export function findCycle(
  id: string,
  deps: readonly string[],
  depsOf: (id: string) => readonly string[] | undefined,
): string[] | null {
  const visited = new Set<string>();
  const visit = (node: string, path: string[]): string[] | null => {
    if (node === id) return path;
    if (visited.has(node)) return null;
    visited.add(node);
    const next = depsOf(node);
    if (!next) return null;
    for (const dep of next) {
      const cycle = visit(dep, [...path, node]);
      if (cycle) return cycle;
    }
    return null;
  };
  for (const dep of deps) {
    const cycle = visit(dep, [id]);
    if (cycle) return cycle;
  }
  return null;
}

export class TimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimeoutError";
  }
}
