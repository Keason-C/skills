// taskflow: a dependency-aware async task scheduler. See BRIEF.md.
// The public API below is fixed: keep these names, types and signatures.

import { type Deferred, findCycle, quietDeferred, TimeoutError } from "./internal.js";

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

interface Task {
  readonly id: string;
  /** Position in add order; breaks ties between tasks made ready by the same transition. */
  readonly index: number;
  readonly run: (ctx: TaskContext) => Promise<unknown>;
  readonly deps: readonly string[];
  readonly priority: number;
  readonly retries: number;
  readonly backoffMs: number;
  readonly timeoutMs: number | undefined;
  state: TaskState;
  /** Attempts started so far. */
  attempts: number;
  /** The ready transition that last queued this task. */
  readySeq: number;
  /** Identifies the current running attempt; settlements of any other attempt are ignored. */
  attemptToken: object | undefined;
  controller: AbortController | undefined;
  timeoutTimer: unknown;
  backoffTimer: unknown;
  value: unknown;
  error: TaskError | undefined;
  /** Settles the promise returned by `result()`. */
  readonly result: Deferred<unknown>;
}

const FINISHED: ReadonlySet<TaskState> = new Set(["succeeded", "failed", "cancelled"]);

/** Ready order: higher priority first, then earlier ready transition, then add order. */
function startsBefore(a: Task, b: Task): boolean {
  if (a.priority !== b.priority) return a.priority > b.priority;
  if (a.readySeq !== b.readySeq) return a.readySeq < b.readySeq;
  return a.index < b.index;
}

type Listeners = { [E in keyof SchedulerEvents]: SchedulerEvents[E][] };

export class Scheduler {
  private readonly concurrency: number;
  private readonly clock: Clock;
  private readonly tasks = new Map<string, Task>();
  /** Added tasks that depend on an id (which may not be added yet), in add order. */
  private readonly dependents = new Map<string, Task[]>();
  private readonly queued = new Set<Task>();
  private readonly listeners: Listeners = { start: [], success: [], retry: [], failure: [], cancel: [], idle: [] };
  private idleWaiters: (() => void)[] = [];
  private started = false;
  private running = 0;
  /** Tasks waiting, queued, running or retrying. */
  private active = 0;
  /** Whether the scheduler has been busy since it was last idle (so `idle` is due when active hits 0). */
  private busy = false;
  private readySeq = 0;
  /** Nesting depth of scheduler operations; dispatch and the idle check run when the outermost one ends. */
  private depth = 0;

  constructor(options: SchedulerOptions) {
    if (!Number.isInteger(options.concurrency) || options.concurrency < 1) {
      throw new RangeError(`concurrency must be an integer >= 1, got ${options.concurrency}`);
    }
    this.concurrency = options.concurrency;
    this.clock = options.clock ?? systemClock;
  }

  add<T>(spec: TaskSpec<T>): void {
    const task = this.createTask(spec);
    this.operate(() => {
      this.tasks.set(task.id, task);
      for (const dep of task.deps) {
        let list = this.dependents.get(dep);
        if (!list) this.dependents.set(dep, (list = []));
        list.push(task);
      }
      const doomedBy = task.deps.map((dep) => this.tasks.get(dep)).find((dep) => dep && (dep.state === "failed" || dep.state === "cancelled"));
      if (doomedBy) {
        task.state = "cancelled";
        this.finish(task, new TaskError(task.id, "dependency", 0, doomedBy.error));
        return;
      }
      this.active++;
      this.busy = true;
      if (this.depsSucceeded(task)) this.makeReady([task]);
    });
  }

  start(): void {
    this.operate(() => {
      this.started = true;
    });
  }

  pause(): void {
    this.started = false;
  }

  cancel(id: string, reason?: unknown): boolean {
    const task = this.tasks.get(id);
    if (!task || FINISHED.has(task.state)) return false;
    this.operate(() => {
      const controller = task.controller;
      this.stopAttempt(task);
      this.clearBackoff(task);
      this.queued.delete(task);
      task.state = "cancelled";
      this.active--;
      const error = new TaskError(id, "cancelled", task.attempts, reason);
      controller?.abort(error);
      this.finish(task, error);
    });
    return true;
  }

  state(id: string): TaskState {
    return this.get(id).state;
  }

  result<T = unknown>(id: string): Promise<T> {
    return this.get(id).result.promise as Promise<T>;
  }

  onIdle(): Promise<void> {
    // While an idle transition is pending (busy with nothing active), wait for it to be announced.
    if (this.active === 0 && !this.busy) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.push(resolve));
  }

  on<E extends keyof SchedulerEvents>(event: E, listener: SchedulerEvents[E]): () => void {
    const list = this.listeners[event];
    list.push(listener);
    return () => {
      const i = list.indexOf(listener);
      if (i >= 0) list.splice(i, 1);
    };
  }

  private get(id: string): Task {
    const task = this.tasks.get(id);
    if (!task) throw new Error(`unknown task: ${id}`);
    return task;
  }

  private createTask<T>(spec: TaskSpec<T>): Task {
    if (typeof spec.run !== "function") throw new TypeError(`task ${spec.id}: run must be a function`);
    const priority = spec.priority ?? 0;
    const retries = spec.retries ?? 0;
    const backoffMs = spec.backoffMs ?? 0;
    const timeoutMs = spec.timeoutMs;
    if (!Number.isFinite(priority)) throw new RangeError(`task ${spec.id}: priority must be finite`);
    if (!Number.isInteger(retries) || retries < 0) throw new RangeError(`task ${spec.id}: retries must be an integer >= 0`);
    if (!(backoffMs >= 0) || backoffMs === Infinity) throw new RangeError(`task ${spec.id}: backoffMs must be a finite number >= 0`);
    if (timeoutMs !== undefined && !(timeoutMs > 0)) throw new RangeError(`task ${spec.id}: timeoutMs must be > 0`);
    if (this.tasks.has(spec.id)) throw new Error(`duplicate task id: ${spec.id}`);
    const deps = [...new Set(spec.deps ?? [])];
    const cycle = findCycle(spec.id, deps, (id) => this.tasks.get(id)?.deps);
    if (cycle) throw new CycleError(cycle);
    return {
      id: spec.id,
      index: this.tasks.size,
      run: spec.run,
      deps,
      priority,
      retries,
      backoffMs,
      timeoutMs,
      state: "waiting",
      attempts: 0,
      readySeq: 0,
      attemptToken: undefined,
      controller: undefined,
      timeoutTimer: undefined,
      backoffTimer: undefined,
      value: undefined,
      error: undefined,
      result: quietDeferred(),
    };
  }

  /**
   * Runs a state change. Nested calls (from listeners or a task's run) just apply their changes;
   * the outermost call then dispatches ready tasks and checks for idleness before returning.
   */
  private operate(change: () => void): void {
    this.depth++;
    try {
      change();
    } finally {
      this.depth--;
    }
    if (this.depth === 0) this.dispatchAndCheckIdle();
  }

  private dispatchAndCheckIdle(): void {
    this.depth++;
    try {
      for (;;) {
        this.dispatch();
        if (!this.busy || this.active > 0) break;
        this.busy = false;
        const waiters = this.idleWaiters;
        this.idleWaiters = [];
        for (const resolve of waiters) resolve();
        this.emit("idle");
      }
    } finally {
      this.depth--;
    }
  }

  private dispatch(): void {
    while (this.started && this.running < this.concurrency) {
      let next: Task | undefined;
      for (const task of this.queued) {
        if (!next || startsBefore(task, next)) next = task;
      }
      if (!next) return;
      this.startAttempt(next);
    }
  }

  private startAttempt(task: Task): void {
    this.queued.delete(task);
    task.state = "running";
    this.running++;
    const attempt = ++task.attempts;
    const token = {};
    const controller = new AbortController();
    task.attemptToken = token;
    task.controller = controller;
    if (task.timeoutMs !== undefined && task.timeoutMs !== Infinity) {
      task.timeoutTimer = this.clock.setTimeout(() => this.operate(() => this.timeOut(task, token)), task.timeoutMs);
    }
    this.emit("start", task.id, attempt);
    // A start listener may have cancelled the task; then its run is never invoked.
    if (task.attemptToken !== token) return;
    const deps: Record<string, unknown> = {};
    for (const dep of task.deps) deps[dep] = this.tasks.get(dep)?.value;
    let pending: Promise<unknown>;
    try {
      pending = Promise.resolve(task.run({ signal: controller.signal, attempt, deps }));
    } catch (error) {
      pending = Promise.reject(error);
    }
    pending.then(
      (value) => this.operate(() => this.attemptSucceeded(task, token, value)),
      (error) => this.operate(() => this.attemptRejected(task, token, error)),
    );
  }

  private attemptSucceeded(task: Task, token: object, value: unknown): void {
    if (task.attemptToken !== token) return;
    this.stopAttempt(task);
    task.state = "succeeded";
    task.value = value;
    this.active--;
    task.result.resolve(value);
    this.emit("success", task.id, value);
    const ready = (this.dependents.get(task.id) ?? []).filter((t) => t.state === "waiting" && this.depsSucceeded(t));
    this.makeReady(ready);
  }

  private attemptRejected(task: Task, token: object, error: unknown): void {
    if (task.attemptToken !== token) return;
    this.stopAttempt(task);
    this.attemptFailed(task, error, new TaskError(task.id, "failed", task.attempts, error));
  }

  private timeOut(task: Task, token: object): void {
    if (task.attemptToken !== token) return;
    task.timeoutTimer = undefined;
    const controller = task.controller;
    this.stopAttempt(task);
    const message = `task ${task.id} attempt ${task.attempts} timed out after ${task.timeoutMs} ms`;
    const error = new TaskError(task.id, "timeout", task.attempts, new TimeoutError(message), message);
    this.attemptFailed(task, error, error, controller);
  }

  /**
   * Handles a failed attempt (the task's slot is already released): schedules a retry if any
   * are left, otherwise fails the task. `controller`, if given, is aborted with `error` once the
   * task's new state is in place.
   */
  private attemptFailed(task: Task, attemptError: unknown, finalError: TaskError, controller?: AbortController): void {
    if (task.attempts <= task.retries) {
      const delay = task.backoffMs * 2 ** (task.attempts - 1);
      task.state = "retrying";
      if (delay > 0) {
        task.backoffTimer = this.clock.setTimeout(
          () =>
            this.operate(() => {
              task.backoffTimer = undefined;
              if (task.state === "retrying") this.makeReady([task]);
            }),
          delay,
        );
      }
      controller?.abort(attemptError);
      if (task.state !== "retrying") return;
      this.emit("retry", task.id, task.attempts + 1, delay, attemptError);
      if (delay === 0 && task.state === "retrying") this.makeReady([task]);
      return;
    }
    task.state = "failed";
    this.active--;
    controller?.abort(attemptError);
    this.finish(task, finalError);
  }

  /** Releases the slot and timeout timer of the task's running attempt, if it has one. */
  private stopAttempt(task: Task): void {
    if (task.attemptToken === undefined) return;
    task.attemptToken = undefined;
    task.controller = undefined;
    this.running--;
    if (task.timeoutTimer !== undefined) {
      this.clock.clearTimeout(task.timeoutTimer);
      task.timeoutTimer = undefined;
    }
  }

  private clearBackoff(task: Task): void {
    if (task.backoffTimer === undefined) return;
    this.clock.clearTimeout(task.backoffTimer);
    task.backoffTimer = undefined;
  }

  /**
   * Completes a task that has just been put in the "failed" or "cancelled" state: settles its
   * result, emits its event, then cancels everything that transitively depends on it.
   */
  private finish(task: Task, error: TaskError): void {
    task.error = error;
    task.result.reject(error);
    this.emit(task.state === "failed" ? "failure" : "cancel", task.id, error);
    this.cascade(task);
  }

  /**
   * Cancels every unfinished task that transitively depends on `root`. All of them change state
   * first; their events follow in add order. Each one's cause is the error of the dependency
   * through which the cascade reached it.
   */
  private cascade(root: Task): void {
    const affected: Task[] = [];
    const frontier = [root];
    for (let i = 0; i < frontier.length; i++) {
      const from = frontier[i]!;
      for (const task of this.dependents.get(from.id) ?? []) {
        if (FINISHED.has(task.state)) continue;
        // Only waiting tasks can be reached: anything further along had all its deps succeed.
        task.state = "cancelled";
        this.active--;
        task.error = new TaskError(task.id, "dependency", task.attempts, from.error);
        affected.push(task);
        frontier.push(task);
      }
    }
    affected.sort((a, b) => a.index - b.index);
    for (const task of affected) {
      task.result.reject(task.error);
      this.emit("cancel", task.id, task.error!);
    }
  }

  private depsSucceeded(task: Task): boolean {
    return task.deps.every((dep) => this.tasks.get(dep)?.state === "succeeded");
  }

  /** Queues tasks that became ready in one transition; ties among them go by add order. */
  private makeReady(tasks: Task[]): void {
    if (tasks.length === 0) return;
    const seq = ++this.readySeq;
    for (const task of tasks) {
      task.state = "queued";
      task.readySeq = seq;
      this.queued.add(task);
    }
  }

  private emit<E extends keyof SchedulerEvents>(event: E, ...args: Parameters<SchedulerEvents[E]>): void {
    for (const listener of [...this.listeners[event]]) {
      try {
        (listener as (...a: Parameters<SchedulerEvents[E]>) => void)(...args);
      } catch {
        // Listener errors are swallowed so they cannot corrupt scheduler state.
      }
    }
  }
}
