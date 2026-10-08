// taskflow: a dependency-aware async task scheduler. See BRIEF.md.
// The public API below is fixed: keep these names, types and signatures.

export interface Clock {
  now(): number;
  setTimeout(callback: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export const systemClock: Clock = {
  now: () => Date.now(),
  setTimeout: (callback, ms) => setTimeout(callback, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

export type TaskState =
  | "waiting"
  | "queued"
  | "running"
  | "retrying"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface TaskContext {
  signal: AbortSignal;
  attempt: number;
  deps: Record<string, unknown>;
}

export interface TaskSpec<T = unknown> {
  id: string;
  run: (ctx: TaskContext) => Promise<T>;
  deps?: string[];
  priority?: number;
  retries?: number;
  backoffMs?: number;
  timeoutMs?: number;
}

export type TaskErrorKind = "failed" | "timeout" | "cancelled" | "dependency";

export class TaskError extends Error {
  constructor(
    readonly taskId: string,
    readonly kind: TaskErrorKind,
    readonly attempts: number,
    override readonly cause?: unknown,
    message?: string,
  ) {
    super(message ?? `task ${taskId} ${kind}`);
    this.name = "TaskError";
  }
}

export class CycleError extends Error {
  constructor(readonly cycle: string[]) {
    super(`dependency cycle: ${cycle.join(" -> ")}`);
    this.name = "CycleError";
  }
}

export interface SchedulerEvents {
  start: (id: string, attempt: number) => void;
  success: (id: string, value: unknown) => void;
  retry: (id: string, nextAttempt: number, delayMs: number, error: unknown) => void;
  failure: (id: string, error: TaskError) => void;
  cancel: (id: string, error: TaskError) => void;
  idle: () => void;
}

export interface SchedulerOptions {
  concurrency: number;
  clock?: Clock;
}


// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

type Listener = (...args: any[]) => void;

/** One started attempt of a task. Identity is used to ignore stale settlements. */
interface Attempt {
  readonly number: number;
  readonly controller: AbortController;
  timeoutHandle: unknown;
  hasTimeout: boolean;
}

interface Task {
  readonly id: string;
  readonly addSeq: number;
  readonly run: (ctx: TaskContext) => Promise<unknown>;
  readonly deps: readonly string[];
  readonly priority: number;
  readonly retries: number;
  readonly backoffMs: number;
  readonly timeoutMs: number | undefined;
  state: TaskState;
  /** Number of distinct deps that have not succeeded yet. */
  remaining: number;
  /** Attempts started so far. */
  attempts: number;
  /** Order key among ready tasks (assigned each time the task becomes ready). */
  readySeq: number;
  current: Attempt | undefined;
  backoffHandle: unknown;
  hasBackoff: boolean;
  value: unknown;
  error: TaskError | undefined;
  readonly promise: Promise<unknown>;
  readonly resolve: (value: unknown) => void;
  readonly reject: (error: TaskError) => void;
}

const FINISHED: ReadonlySet<TaskState> = new Set<TaskState>(["succeeded", "failed", "cancelled"]);

function isFinished(task: Task): boolean {
  return FINISHED.has(task.state);
}

export class Scheduler {
  readonly #concurrency: number;
  readonly #clock: Clock;
  readonly #tasks = new Map<string, Task>();
  /** dep id -> tasks that list it in `deps` (may be registered before the dep is added). */
  readonly #dependents = new Map<string, Task[]>();
  readonly #ready: Task[] = [];
  readonly #listeners = new Map<keyof SchedulerEvents, Array<{ fn: Listener }>>();
  #idleWaiters: Array<() => void> = [];
  #started = false;
  #running = 0;
  #unfinished = 0;
  #addSeq = 0;
  #readySeq = 0;
  #depth = 0;
  #wasIdle = true;

  constructor(options: SchedulerOptions) {
    const concurrency = options?.concurrency;
    if (typeof concurrency !== "number" || !Number.isInteger(concurrency) || concurrency < 1) {
      throw new RangeError(`concurrency must be an integer >= 1 (got ${String(concurrency)})`);
    }
    this.#concurrency = concurrency;
    this.#clock = options.clock ?? systemClock;
  }

  // ---- public API ---------------------------------------------------------

  add<T>(spec: TaskSpec<T>): void {
    const id = spec?.id;
    if (typeof id !== "string") throw new TypeError("task id must be a string");
    if (typeof spec.run !== "function") throw new TypeError(`task ${id}: run must be a function`);
    if (this.#tasks.has(id)) throw new Error(`duplicate task id: ${id}`);

    const priority = spec.priority ?? 0;
    if (typeof priority !== "number" || !Number.isFinite(priority)) {
      throw new RangeError(`task ${id}: priority must be a finite number`);
    }
    const retries = spec.retries ?? 0;
    if (typeof retries !== "number" || !Number.isInteger(retries) || retries < 0) {
      throw new RangeError(`task ${id}: retries must be an integer >= 0`);
    }
    const backoffMs = spec.backoffMs ?? 0;
    if (typeof backoffMs !== "number" || !Number.isFinite(backoffMs) || backoffMs < 0) {
      throw new RangeError(`task ${id}: backoffMs must be a finite number >= 0`);
    }
    const timeoutMs = spec.timeoutMs;
    if (timeoutMs !== undefined && (typeof timeoutMs !== "number" || !(timeoutMs > 0))) {
      throw new RangeError(`task ${id}: timeoutMs must be > 0`);
    }
    const rawDeps = spec.deps ?? [];
    if (!Array.isArray(rawDeps)) throw new TypeError(`task ${id}: deps must be an array`);
    const deps: string[] = [];
    for (const d of rawDeps) {
      if (typeof d !== "string") throw new TypeError(`task ${id}: dependency ids must be strings`);
      if (!deps.includes(d)) deps.push(d);
    }

    const cycle = this.#findCycle(id, deps);
    if (cycle) throw new CycleError(cycle);

    // ---- validation done: from here on the scheduler is mutated ----
    this.#enter();
    try {
      let resolve!: (value: unknown) => void;
      let reject!: (error: TaskError) => void;
      const promise = new Promise<unknown>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      promise.catch(() => {}); // never an unhandled rejection, whether or not result() is used

      const task: Task = {
        id,
        addSeq: this.#addSeq++,
        run: spec.run as (ctx: TaskContext) => Promise<unknown>,
        deps,
        priority,
        retries,
        backoffMs,
        timeoutMs,
        state: "waiting",
        remaining: 0,
        attempts: 0,
        readySeq: 0,
        current: undefined,
        backoffHandle: undefined,
        hasBackoff: false,
        value: undefined,
        error: undefined,
        promise,
        resolve,
        reject,
      };
      this.#tasks.set(id, task);
      this.#unfinished++;

      let deadDep: Task | undefined;
      for (const d of deps) {
        let list = this.#dependents.get(d);
        if (!list) this.#dependents.set(d, (list = []));
        list.push(task);
        const dep = this.#tasks.get(d);
        if (dep?.state === "succeeded") continue;
        if (dep && (dep.state === "failed" || dep.state === "cancelled")) deadDep ??= dep;
        task.remaining++;
      }

      if (deadDep) {
        // A dependency already ended failed/cancelled: cancel immediately (and cascade to
        // tasks that forward-referenced this one).
        this.#finish(task, "cancelled", new TaskError(id, "dependency", 0, deadDep.error));
      } else if (task.remaining === 0) {
        this.#enqueue([task]);
      }
    } finally {
      this.#exit();
    }
  }

  start(): void {
    if (this.#started) return;
    this.#enter();
    try {
      this.#started = true;
    } finally {
      this.#exit();
    }
  }

  pause(): void {
    this.#started = false;
  }

  cancel(id: string, reason?: unknown): boolean {
    const task = this.#tasks.get(id);
    if (!task || isFinished(task)) return false;
    this.#enter();
    try {
      this.#finish(task, "cancelled", new TaskError(id, "cancelled", task.attempts, reason));
    } finally {
      this.#exit();
    }
    return true;
  }

  state(id: string): TaskState {
    const task = this.#tasks.get(id);
    if (!task) throw new Error(`unknown task: ${id}`);
    return task.state;
  }

  result<T = unknown>(id: string): Promise<T> {
    const task = this.#tasks.get(id);
    if (!task) throw new Error(`unknown task: ${id}`);
    return task.promise as Promise<T>;
  }

  onIdle(): Promise<void> {
    if (this.#unfinished === 0) return Promise.resolve();
    return new Promise<void>((resolve) => this.#idleWaiters.push(resolve));
  }

  on<E extends keyof SchedulerEvents>(event: E, listener: SchedulerEvents[E]): () => void {
    let list = this.#listeners.get(event);
    if (!list) this.#listeners.set(event, (list = []));
    const entry = { fn: listener as Listener };
    list.push(entry);
    return () => {
      const current = this.#listeners.get(event);
      if (!current) return;
      const i = current.indexOf(entry);
      if (i >= 0) current.splice(i, 1);
    };
  }

  // ---- transitions --------------------------------------------------------

  /**
   * Every externally triggered operation (public mutator, timer callback, settled-attempt
   * reaction) runs between #enter/#exit. Only the outermost #exit dispatches and checks for
   * idleness, so nested calls made from listeners or from a run() body never interleave
   * dispatch with an in-progress transition.
   */
  #enter(): void {
    this.#depth++;
  }

  #exit(): void {
    if (this.#depth > 1) {
      this.#depth--;
      return;
    }
    try {
      for (;;) {
        this.#pump();
        const idle = this.#unfinished === 0;
        if (idle && !this.#wasIdle) {
          this.#wasIdle = true;
          const waiters = this.#idleWaiters;
          this.#idleWaiters = [];
          for (const w of waiters) w();
          this.#emit("idle");
          continue; // an idle listener may have added work
        }
        if (!idle) this.#wasIdle = false;
        if (this.#canDispatch()) continue;
        break;
      }
    } finally {
      this.#depth = 0;
    }
  }

  #canDispatch(): boolean {
    return this.#started && this.#running < this.#concurrency && this.#ready.length > 0;
  }

  #pump(): void {
    while (this.#canDispatch()) {
      const task = this.#takeNext();
      if (!task) break;
      this.#launch(task);
    }
  }

  #takeNext(): Task | undefined {
    let best = -1;
    for (let i = 0; i < this.#ready.length; i++) {
      const t = this.#ready[i]!;
      if (best < 0) {
        best = i;
        continue;
      }
      const b = this.#ready[best]!;
      if (
        t.priority > b.priority ||
        (t.priority === b.priority &&
          (t.readySeq < b.readySeq || (t.readySeq === b.readySeq && t.addSeq < b.addSeq)))
      ) {
        best = i;
      }
    }
    if (best < 0) return undefined;
    return this.#ready.splice(best, 1)[0];
  }

  /** Marks tasks ready. Tasks passed together became ready at the same moment. */
  #enqueue(tasks: Task[]): void {
    const sorted = [...tasks].sort((a, b) => a.addSeq - b.addSeq);
    for (const t of sorted) {
      t.state = "queued";
      t.readySeq = this.#readySeq++;
      this.#ready.push(t);
    }
  }

  #launch(task: Task): void {
    task.attempts++;
    task.state = "running";
    this.#running++;
    const attempt: Attempt = {
      number: task.attempts,
      controller: new AbortController(),
      timeoutHandle: undefined,
      hasTimeout: false,
    };
    task.current = attempt;
    const timeoutMs = task.timeoutMs;
    if (timeoutMs !== undefined && Number.isFinite(timeoutMs)) {
      attempt.hasTimeout = true;
      attempt.timeoutHandle = this.#clock.setTimeout(() => this.#onTimeout(task, attempt), timeoutMs);
    }

    this.#emit("start", task.id, attempt.number);
    if (task.current !== attempt) return; // cancelled by a start listener

    const deps = Object.fromEntries(task.deps.map((d) => [d, this.#tasks.get(d)!.value]));
    const ctx: TaskContext = { signal: attempt.controller.signal, attempt: attempt.number, deps };
    let promise: Promise<unknown>;
    try {
      promise = Promise.resolve(task.run(ctx));
    } catch (err) {
      promise = Promise.reject(err);
    }
    promise.then(
      (value) => this.#onSettled(task, attempt, true, value),
      (error) => this.#onSettled(task, attempt, false, error),
    );
  }

  /** Ends the current attempt: clears its timeout and frees its slot. */
  #endAttempt(task: Task, attempt: Attempt): void {
    if (attempt.hasTimeout) {
      attempt.hasTimeout = false;
      this.#clock.clearTimeout(attempt.timeoutHandle);
    }
    task.current = undefined;
    this.#running--;
  }

  #onSettled(task: Task, attempt: Attempt, ok: boolean, valueOrError: unknown): void {
    if (task.current !== attempt) return; // timed out or cancelled: ignore
    this.#enter();
    try {
      this.#endAttempt(task, attempt);
      if (ok) this.#succeed(task, valueOrError);
      else this.#attemptFailed(task, valueOrError, valueOrError, "failed");
    } finally {
      this.#exit();
    }
  }

  #onTimeout(task: Task, attempt: Attempt): void {
    if (task.current !== attempt || !attempt.hasTimeout) return;
    attempt.hasTimeout = false; // the timer has fired; nothing to clear
    this.#enter();
    try {
      const err = new TaskError(
        task.id,
        "timeout",
        attempt.number,
        undefined,
        `task ${task.id} attempt ${attempt.number} timed out after ${task.timeoutMs}ms`,
      );
      this.#endAttempt(task, attempt);
      attempt.controller.abort(err);
      this.#attemptFailed(task, err, undefined, "timeout", err);
    } finally {
      this.#exit();
    }
  }

  #succeed(task: Task, value: unknown): void {
    task.state = "succeeded";
    task.value = value;
    this.#unfinished--;
    task.resolve(value);
    this.#emit("success", task.id, value);

    const nowReady: Task[] = [];
    for (const dep of this.#dependents.get(task.id) ?? []) {
      if (dep.state !== "waiting") continue;
      if (--dep.remaining === 0) nowReady.push(dep);
    }
    if (nowReady.length > 0) this.#enqueue(nowReady);
  }

  /**
   * An attempt failed with `retryError` (what the retry event reports). Retries if attempts
   * remain, otherwise ends the task failed with `kind`/`cause` (or `finalError` if given).
   */
  #attemptFailed(
    task: Task,
    retryError: unknown,
    cause: unknown,
    kind: "failed" | "timeout",
    finalError?: TaskError,
  ): void {
    if (task.attempts <= task.retries) {
      const delay = task.backoffMs * 2 ** (task.attempts - 1);
      task.state = "retrying";
      if (delay > 0) {
        task.hasBackoff = true;
        const handle = this.#clock.setTimeout(() => this.#onBackoff(task, handle), delay);
        task.backoffHandle = handle;
      }
      this.#emit("retry", task.id, task.attempts + 1, delay, retryError);
      if (delay <= 0 && task.state === "retrying") this.#enqueue([task]);
      return;
    }
    this.#finish(task, "failed", finalError ?? new TaskError(task.id, kind, task.attempts, cause));
  }

  #onBackoff(task: Task, handle: unknown): void {
    if (task.state !== "retrying" || !task.hasBackoff || task.backoffHandle !== handle) return;
    task.hasBackoff = false;
    task.backoffHandle = undefined;
    this.#enter();
    try {
      this.#enqueue([task]);
    } finally {
      this.#exit();
    }
  }

  /**
   * Ends `task` failed or cancelled from any unfinished state, releasing whatever it holds,
   * emits its event, then cascades "dependency" cancellations to its transitive dependents.
   */
  #finish(task: Task, state: "failed" | "cancelled", error: TaskError): void {
    const prev = task.state;
    task.state = state;
    task.error = error;
    this.#unfinished--;
    if (prev === "queued") {
      const i = this.#ready.indexOf(task);
      if (i >= 0) this.#ready.splice(i, 1);
    } else if (prev === "retrying") {
      if (task.hasBackoff) {
        task.hasBackoff = false;
        this.#clock.clearTimeout(task.backoffHandle);
        task.backoffHandle = undefined;
      }
    } else if (prev === "running" && task.current) {
      const attempt = task.current;
      this.#endAttempt(task, attempt);
      attempt.controller.abort(error);
    }
    task.reject(error);
    this.#emit(state === "failed" ? "failure" : "cancel", task.id, error);
    this.#cascade(task);
  }

  #cascade(root: Task): void {
    // Breadth-first from the root, so each dependent's cause is the TaskError of the direct
    // dependency through which the cancellation first reaches it.
    const causes = new Map<Task, TaskError>();
    const queue: Task[] = [root];
    for (let i = 0; i < queue.length; i++) {
      const from = queue[i]!;
      const fromError = from === root ? root.error : causes.get(from);
      const list = [...(this.#dependents.get(from.id) ?? [])].sort((a, b) => a.addSeq - b.addSeq);
      for (const dep of list) {
        if (isFinished(dep) || causes.has(dep)) continue;
        causes.set(dep, new TaskError(dep.id, "dependency", 0, fromError));
        queue.push(dep);
      }
    }
    const affected = [...causes.keys()].sort((a, b) => a.addSeq - b.addSeq);
    for (const dep of affected) {
      if (isFinished(dep)) continue; // e.g. cancelled explicitly by a listener meanwhile
      const error = causes.get(dep)!;
      dep.state = "cancelled";
      dep.error = error;
      this.#unfinished--;
      dep.reject(error);
      this.#emit("cancel", dep.id, error);
    }
  }

  // ---- helpers ------------------------------------------------------------

  /** Returns the ids on a cycle that adding `id` with `deps` would create, if any. */
  #findCycle(id: string, deps: readonly string[]): string[] | undefined {
    if (deps.includes(id)) return [id];
    const visited = new Set<string>();
    const parent = new Map<string, string>();
    const stack: string[] = [];
    for (const d of deps) {
      if (visited.has(d)) continue;
      visited.add(d);
      parent.set(d, id);
      stack.push(d);
    }
    while (stack.length > 0) {
      const cur = stack.pop()!;
      const task = this.#tasks.get(cur);
      if (!task) continue;
      for (const next of task.deps) {
        if (next === id) {
          const path: string[] = [];
          for (let n: string | undefined = cur; n !== undefined && n !== id; n = parent.get(n)) {
            path.push(n);
          }
          return [id, ...path.reverse()];
        }
        if (visited.has(next)) continue;
        visited.add(next);
        parent.set(next, cur);
        stack.push(next);
      }
    }
    return undefined;
  }

  #emit(event: keyof SchedulerEvents, ...args: unknown[]): void {
    const list = this.#listeners.get(event);
    if (!list || list.length === 0) return;
    for (const { fn } of [...list]) {
      try {
        fn(...args);
      } catch {
        // listener exceptions are swallowed; remaining listeners still run
      }
    }
  }
}
