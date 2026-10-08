// taskflow: a dependency-aware async task scheduler. See BRIEF.md.
// The public API below is fixed: keep these names, types and signatures.

import { Emitter } from "./internal/emitter.js";
import { Heap } from "./internal/heap.js";

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

function validateSpec(spec: TaskSpec<unknown>): void {
  if (typeof spec.id !== "string" || spec.id === "") throw new TypeError("task id must be a non-empty string");
  if (typeof spec.run !== "function") throw new TypeError(`task ${spec.id}: run must be a function`);
  if (spec.deps !== undefined && (!Array.isArray(spec.deps) || !spec.deps.every((d) => typeof d === "string"))) {
    throw new TypeError(`task ${spec.id}: deps must be an array of task ids`);
  }
  const { priority, retries, backoffMs, timeoutMs } = spec;
  if (priority !== undefined && !Number.isFinite(priority)) {
    throw new RangeError(`task ${spec.id}: priority must be a finite number`);
  }
  if (retries !== undefined && !(Number.isInteger(retries) && retries >= 0)) {
    throw new RangeError(`task ${spec.id}: retries must be an integer >= 0`);
  }
  if (backoffMs !== undefined && !(Number.isFinite(backoffMs) && backoffMs >= 0)) {
    throw new RangeError(`task ${spec.id}: backoffMs must be a finite number >= 0`);
  }
  if (timeoutMs !== undefined && !(Number.isFinite(timeoutMs) && timeoutMs > 0)) {
    throw new RangeError(`task ${spec.id}: timeoutMs must be a finite number > 0`);
  }
}

function isFinished(task: Task): boolean {
  return task.state === "succeeded" || isDead(task);
}

function isDead(task: Task): boolean {
  return task.state === "failed" || task.state === "cancelled";
}

/** One invocation of a task's `run`; settlements of stale attempts are ignored. */
interface Attempt {
  readonly controller: AbortController;
  timer?: unknown;
}

interface Task {
  readonly id: string;
  readonly run: (ctx: TaskContext) => Promise<unknown>;
  readonly priority: number;
  readonly addIndex: number;
  readonly retries: number;
  readonly backoffMs: number;
  readonly timeoutMs: number | undefined;
  /** The attempt occupying a slot while `running`. */
  current?: Attempt;
  /** Pending backoff timer while `retrying`. */
  backoffTimer?: unknown;
  /** Position in the ready order: tasks made ready together are numbered in add order. */
  readySeq: number;
  /** De-duplicated dependency ids, in declared order. */
  readonly deps: readonly string[];
  /** Added tasks that list this one in their deps, in add order. */
  readonly dependents: Task[];
  /** Dependencies that have not succeeded yet (including ones not added yet). */
  unmet: number;
  state: TaskState;
  attempts: number;
  value?: unknown;
  error?: TaskError;
  readonly result: Promise<unknown>;
  readonly resolve: (value: unknown) => void;
  readonly reject: (error: TaskError) => void;
}

export class Scheduler {
  private readonly concurrency: number;
  private readonly clock: Clock;
  private readonly tasks = new Map<string, Task>();
  /** Ready tasks: higher priority first, then earlier readiness. May hold stale (cancelled) entries. */
  private readonly ready = new Heap<Task>(
    (a, b) => a.priority > b.priority || (a.priority === b.priority && a.readySeq < b.readySeq),
  );
  private nextReadySeq = 0;
  private idleWaiters: (() => void)[] = [];
  /** Tasks waiting on an id that has not been added yet, in add order. */
  private readonly forwardRefs = new Map<string, Task[]>();
  private readonly events = new Emitter<SchedulerEvents>(["start", "success", "retry", "failure", "cancel", "idle"]);
  private started = false;
  /** Tasks not yet succeeded, failed or cancelled. */
  private unfinished = 0;
  /** Whether `idle` has fired since the scheduler last had unfinished work; it fires on the false -> true edge. */
  private idleEmitted = true;
  private running = 0;
  /** Nesting depth of public operations; dispatch happens when the outermost one ends. */
  private depth = 0;

  constructor(options: SchedulerOptions) {
    if (!Number.isInteger(options.concurrency) || options.concurrency < 1) {
      throw new RangeError(`concurrency must be an integer >= 1, got ${options.concurrency}`);
    }
    this.concurrency = options.concurrency;
    this.clock = options.clock ?? systemClock;
  }

  add<T>(spec: TaskSpec<T>): void {
    validateSpec(spec);
    if (this.tasks.has(spec.id)) throw new Error(`duplicate task id: ${spec.id}`);
    const deps = [...new Set(spec.deps ?? [])];
    const cycle = this.findCycle(spec.id, deps);
    if (cycle) throw new CycleError(cycle);
    this.op(() => {
      let resolve!: (value: unknown) => void;
      let reject!: (error: TaskError) => void;
      const result = new Promise<unknown>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      result.catch(() => {});
      const task: Task = {
        id: spec.id,
        run: spec.run,
        priority: spec.priority ?? 0,
        addIndex: this.tasks.size,
        retries: spec.retries ?? 0,
        backoffMs: spec.backoffMs ?? 0,
        timeoutMs: spec.timeoutMs,
        readySeq: 0,
        deps,
        dependents: this.forwardRefs.get(spec.id) ?? [],
        unmet: 0,
        state: "waiting",
        attempts: 0,
        result,
        resolve,
        reject,
      };
      this.forwardRefs.delete(task.id);
      this.tasks.set(task.id, task);
      for (const depId of deps) {
        const dep = this.tasks.get(depId);
        if (dep) dep.dependents.push(task);
        else if (this.forwardRefs.has(depId)) this.forwardRefs.get(depId)!.push(task);
        else this.forwardRefs.set(depId, [task]);
        if (dep?.state !== "succeeded") task.unmet++;
      }
      this.unfinished++;
      const deadDep = this.firstDeadDep(task);
      if (deadDep) {
        this.finish(task, "cancelled", new TaskError(task.id, "dependency", 0, deadDep.error));
        return;
      }
      this.idleEmitted = false;
      if (task.unmet === 0) this.makeReady(task);
    });
  }

  start(): void {
    this.op(() => {
      this.started = true;
    });
  }

  pause(): void {
    this.started = false;
  }

  cancel(id: string, reason?: unknown): boolean {
    const task = this.tasks.get(id);
    if (!task || isFinished(task)) return false;
    this.op(() => {
      const attempt = task.current;
      if (attempt) this.endAttempt(task, attempt);
      if (task.backoffTimer !== undefined) this.clock.clearTimeout(task.backoffTimer);
      task.backoffTimer = undefined;
      // A queued task stays in the ready heap; dispatch skips it because it is no longer queued.
      const error = new TaskError(task.id, "cancelled", task.attempts, reason);
      this.finish(task, "cancelled", error, attempt?.controller);
    });
    return true;
  }

  state(id: string): TaskState {
    return this.get(id).state;
  }

  result<T = unknown>(id: string): Promise<T> {
    return this.get(id).result as Promise<T>;
  }

  onIdle(): Promise<void> {
    if (this.unfinished === 0) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.push(resolve));
  }

  on<E extends keyof SchedulerEvents>(event: E, listener: SchedulerEvents[E]): () => void {
    return this.events.on(event, listener);
  }

  /**
   * The cycle that adding `id` with `deps` would close, as the path from `id` along dependency
   * edges (DFS in declared order), or undefined. Task states are irrelevant: this is structural.
   */
  private findCycle(id: string, deps: readonly string[]): string[] | undefined {
    // Only an existing forward reference to `id` (or a self-dependency) can close a cycle.
    if (!this.forwardRefs.has(id) && !deps.includes(id)) return undefined;
    const path = [id];
    const visited = new Set<string>();
    const stack = [deps[Symbol.iterator]()];
    while (stack.length > 0) {
      const next = stack[stack.length - 1]!.next();
      if (next.done) {
        stack.pop();
        path.pop();
        continue;
      }
      if (next.value === id) return path;
      const dep = this.tasks.get(next.value);
      if (!dep || visited.has(dep.id)) continue;
      visited.add(dep.id);
      path.push(dep.id);
      stack.push(dep.deps[Symbol.iterator]());
    }
    return undefined;
  }

  /** The first of `task`'s dependencies, in declared order, that failed or was cancelled. */
  private firstDeadDep(task: Task): Task | undefined {
    for (const id of task.deps) {
      const dep = this.tasks.get(id);
      if (dep && isDead(dep)) return dep;
    }
    return undefined;
  }

  private get(id: string): Task {
    const task = this.tasks.get(id);
    if (!task) throw new Error(`unknown task: ${id}`);
    return task;
  }

  /**
   * Runs a state change (public call, timer callback or settle reaction). Calls may nest through
   * `run` and listeners; when the outermost one ends, it drains: dispatches runnable tasks and emits
   * `idle` if the scheduler just became idle.
   */
  private op<R>(fn: () => R): R {
    this.depth++;
    try {
      return fn();
    } finally {
      if (this.depth === 1) this.drain();
      this.depth--;
    }
  }

  private drain(): void {
    for (;;) {
      while (this.started && this.running < this.concurrency) {
        const task = this.ready.pop();
        if (!task) break;
        if (task.state === "queued") this.startAttempt(task);
      }
      if (this.unfinished > 0 || this.idleEmitted) return;
      this.idleEmitted = true;
      const waiters = this.idleWaiters;
      this.idleWaiters = [];
      for (const resolve of waiters) resolve();
      this.events.emit("idle");
    }
  }

  private makeReady(task: Task): void {
    task.state = "queued";
    task.readySeq = this.nextReadySeq++;
    this.ready.push(task);
  }

  private startAttempt(task: Task): void {
    task.state = "running";
    task.attempts++;
    this.running++;
    const attempt: Attempt = { controller: new AbortController() };
    task.current = attempt;
    this.events.emit("start", task.id, task.attempts);
    if (task.current !== attempt) return; // a start listener cancelled it

    if (task.timeoutMs !== undefined) {
      attempt.timer = this.clock.setTimeout(() => this.op(() => this.timeOut(task, attempt)), task.timeoutMs);
    }
    const deps = Object.fromEntries(task.deps.map((id) => [id, this.tasks.get(id)!.value]));
    const ctx: TaskContext = { signal: attempt.controller.signal, attempt: task.attempts, deps };
    let settled: Promise<unknown>;
    try {
      settled = Promise.resolve(task.run(ctx));
    } catch (error) {
      settled = Promise.reject(error);
    }
    settled.then(
      (value) =>
        this.op(() => {
          if (task.current !== attempt) return;
          this.endAttempt(task, attempt);
          this.succeed(task, value);
        }),
      (error: unknown) =>
        this.op(() => {
          if (task.current !== attempt) return;
          this.endAttempt(task, attempt);
          this.failAttempt(task, error, new TaskError(task.id, "failed", task.attempts, error));
        }),
    );
  }

  /** Releases the attempt's slot and timeout timer. */
  private endAttempt(task: Task, attempt: Attempt): void {
    if (attempt.timer !== undefined) this.clock.clearTimeout(attempt.timer);
    attempt.timer = undefined;
    task.current = undefined;
    this.running--;
  }

  private timeOut(task: Task, attempt: Attempt): void {
    if (task.current !== attempt) return;
    attempt.timer = undefined; // it has fired; don't clear it
    this.endAttempt(task, attempt);
    const error = new TaskError(
      task.id,
      "timeout",
      task.attempts,
      undefined,
      `task ${task.id} attempt ${task.attempts} timed out after ${task.timeoutMs}ms`,
    );
    this.failAttempt(task, error, error, attempt.controller);
  }

  private succeed(task: Task, value: unknown): void {
    task.state = "succeeded";
    task.value = value;
    this.unfinished--;
    for (const dependent of task.dependents) {
      if (--dependent.unmet === 0 && dependent.state === "waiting") this.makeReady(dependent);
    }
    this.events.emit("success", task.id, value);
    task.resolve(value);
  }

  /**
   * After a failed attempt (slot already released): schedule a retry, or end the task failed.
   * `attemptError` is what the attempt failed with (reported by `retry`); `finalError` is the task's
   * error if this was its last attempt. `controller`, if given, is aborted once the new state is
   * committed, before any event.
   */
  private failAttempt(task: Task, attemptError: unknown, finalError: TaskError, controller?: AbortController): void {
    if (task.attempts > task.retries) {
      this.finish(task, "failed", finalError, controller);
      return;
    }
    const delay = task.backoffMs * 2 ** (task.attempts - 1);
    task.state = "retrying";
    if (delay > 0) {
      const timer = this.clock.setTimeout(
        () =>
          this.op(() => {
            if (task.backoffTimer !== timer) return;
            task.backoffTimer = undefined;
            this.makeReady(task);
          }),
        delay,
      );
      task.backoffTimer = timer;
    }
    controller?.abort(attemptError);
    this.events.emit("retry", task.id, task.attempts + 1, delay, attemptError);
    if (delay === 0 && task.state === "retrying") this.makeReady(task);
  }

  /**
   * Ends `task` as failed or cancelled and cancels every task waiting on it, transitively. All
   * state changes are committed first (and `controller` aborted); then the task's own event, then
   * the cascade in add order.
   */
  private finish(task: Task, state: "failed" | "cancelled", error: TaskError, controller?: AbortController): void {
    task.state = state;
    task.error = error;
    this.unfinished--;
    const cascade: Task[] = [];
    const toVisit = [task];
    for (let t = toVisit.pop(); t; t = toVisit.pop()) {
      for (const dependent of t.dependents) {
        if (dependent.state !== "waiting") continue;
        dependent.state = "cancelled";
        this.unfinished--;
        cascade.push(dependent);
        toVisit.push(dependent);
      }
    }
    cascade.sort((a, b) => a.addIndex - b.addIndex);
    for (const t of cascade) this.assignDependencyError(t);
    controller?.abort(error);

    this.events.emit(state === "failed" ? "failure" : "cancel", task.id, error);
    for (const t of cascade) this.events.emit("cancel", t.id, t.error!);
    task.reject(error);
    for (const t of cascade) t.reject(t.error!);
  }

  /**
   * Gives a task cancelled by the cascade its error, caused by its first dead dependency (whose
   * own error is assigned first, walking up the chain iteratively).
   */
  private assignDependencyError(task: Task): void {
    const stack = [task];
    while (stack.length > 0) {
      const t = stack[stack.length - 1]!;
      if (t.error) {
        stack.pop();
        continue;
      }
      const dep = this.firstDeadDep(t)!;
      if (dep.error) t.error = new TaskError(t.id, "dependency", 0, dep.error);
      else stack.push(dep);
    }
  }
}
