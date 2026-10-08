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

interface NormalizedSpec {
  readonly id: string;
  readonly run: (ctx: TaskContext) => Promise<unknown>;
  readonly deps: readonly string[];
  readonly priority: number;
  readonly retries: number;
  readonly backoffMs: number;
  readonly timeoutMs: number | undefined;
}

interface Attempt {
  readonly number: number;
  readonly controller: AbortController;
  timer: { readonly handle: unknown } | undefined;
}

interface QueuedPhase {
  readonly kind: "queued";
  readonly moment: number;
}

type TerminalPhase =
  | { readonly kind: "succeeded"; readonly value: unknown }
  | { readonly kind: "failed"; readonly error: TaskError }
  | { readonly kind: "cancelled"; readonly error: TaskError };

type Phase =
  | { readonly kind: "waiting" }
  | QueuedPhase
  | { readonly kind: "running"; readonly attempt: Attempt }
  | { readonly kind: "retrying"; readonly timerHandle: unknown }
  | TerminalPhase;

interface Settlement {
  readonly promise: Promise<unknown>;
  readonly resolve: (value: unknown) => void;
  readonly reject: (error: TaskError) => void;
}

interface Task {
  readonly spec: NormalizedSpec;
  readonly order: number;
  attemptsStarted: number;
  phase: Phase;
  readonly settlement: Settlement;
}

interface ReadyEntry {
  readonly task: Task;
  readonly phase: QueuedPhase;
}

type Subscription<E extends keyof SchedulerEvents> = { readonly fn: SchedulerEvents[E] };
type Listeners = { [E in keyof SchedulerEvents]: Set<Subscription<E>> };

const WAITING: Phase = { kind: "waiting" };

function isTerminal(phase: Phase): phase is TerminalPhase {
  return phase.kind === "succeeded" || phase.kind === "failed" || phase.kind === "cancelled";
}

function createSettlement(): Settlement {
  let resolve: (value: unknown) => void = () => {};
  let reject: (error: TaskError) => void = () => {};
  const promise = new Promise<unknown>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  promise.catch(() => {});
  return { promise, resolve, reject };
}

function normalizeSpec<T>(spec: TaskSpec<T>): NormalizedSpec {
  const priority = spec.priority ?? 0;
  const retries = spec.retries ?? 0;
  const backoffMs = spec.backoffMs ?? 0;
  const { timeoutMs } = spec;
  if (!Number.isFinite(priority)) {
    throw new RangeError(`task ${spec.id}: priority must be a finite number, got ${priority}`);
  }
  if (!Number.isInteger(retries) || retries < 0) {
    throw new RangeError(`task ${spec.id}: retries must be an integer >= 0, got ${retries}`);
  }
  if (!Number.isFinite(backoffMs) || backoffMs < 0) {
    throw new RangeError(`task ${spec.id}: backoffMs must be a finite number >= 0, got ${backoffMs}`);
  }
  if (timeoutMs !== undefined && !(timeoutMs > 0)) {
    throw new RangeError(`task ${spec.id}: timeoutMs must be > 0, got ${timeoutMs}`);
  }
  return {
    id: spec.id,
    run: spec.run,
    deps: [...new Set(spec.deps ?? [])],
    priority,
    retries,
    backoffMs,
    timeoutMs,
  };
}

function isLive(entry: ReadyEntry): boolean {
  return entry.task.phase === entry.phase;
}

function readyBefore(a: ReadyEntry, b: ReadyEntry): boolean {
  if (a.task.spec.priority !== b.task.spec.priority) {
    return a.task.spec.priority > b.task.spec.priority;
  }
  if (a.phase.moment !== b.phase.moment) return a.phase.moment < b.phase.moment;
  return a.task.order < b.task.order;
}

class ReadyQueue {
  private readonly heap: ReadyEntry[] = [];

  push(entry: ReadyEntry): void {
    const heap = this.heap;
    heap.push(entry);
    let i = heap.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      const p = heap[parent];
      if (p === undefined || !readyBefore(entry, p)) break;
      heap[i] = p;
      i = parent;
    }
    heap[i] = entry;
  }

  pop(): Task | undefined {
    for (let entry = this.popEntry(); entry !== undefined; entry = this.popEntry()) {
      if (isLive(entry)) return entry.task;
    }
    return undefined;
  }

  private popEntry(): ReadyEntry | undefined {
    const heap = this.heap;
    const top = heap[0];
    const last = heap.pop();
    if (top === undefined || last === undefined || heap.length === 0) return top;
    let i = 0;
    for (;;) {
      const left = 2 * i + 1;
      const right = left + 1;
      let best = i;
      let bestEntry = last;
      const l = heap[left];
      if (l !== undefined && readyBefore(l, bestEntry)) {
        best = left;
        bestEntry = l;
      }
      const r = heap[right];
      if (r !== undefined && readyBefore(r, bestEntry)) {
        best = right;
        bestEntry = r;
      }
      if (best === i) break;
      heap[i] = bestEntry;
      i = best;
    }
    heap[i] = last;
    return top;
  }
}

export class Scheduler {
  private readonly concurrency: number;
  private readonly clock: Clock;
  private readonly tasks = new Map<string, Task>();
  private readonly dependentsOf = new Map<string, string[]>();
  private readonly ready = new ReadyQueue();
  private readonly listeners: Listeners = {
    start: new Set(),
    success: new Set(),
    retry: new Set(),
    failure: new Set(),
    cancel: new Set(),
    idle: new Set(),
  };
  private readonly pendingEvents: Array<() => void> = [];
  private flushing = false;
  private readonly idleWaiters: Array<() => void> = [];
  private started = false;
  private running = 0;
  private unfinished = 0;
  private moment = 0;
  private depth = 0;

  constructor(options: SchedulerOptions) {
    const { concurrency } = options;
    if (!Number.isInteger(concurrency) || concurrency < 1) {
      throw new RangeError(`concurrency must be an integer >= 1, got ${concurrency}`);
    }
    this.concurrency = concurrency;
    this.clock = options.clock ?? systemClock;
  }

  add<T>(spec: TaskSpec<T>): void {
    if (this.tasks.has(spec.id)) throw new Error(`duplicate task id: ${spec.id}`);
    const normalized = normalizeSpec(spec);
    const cycle = this.findCycleThrough(normalized.id, normalized.deps);
    if (cycle !== undefined) throw new CycleError(cycle);

    this.transaction(() => {
      const task: Task = {
        spec: normalized,
        order: this.tasks.size,
        attemptsStarted: 0,
        phase: WAITING,
        settlement: createSettlement(),
      };
      this.tasks.set(normalized.id, task);
      this.unfinished++;
      for (const dep of normalized.deps) {
        const list = this.dependentsOf.get(dep);
        if (list === undefined) this.dependentsOf.set(dep, [normalized.id]);
        else list.push(normalized.id);
      }

      const blocker = this.firstBrokenDependency(task);
      if (blocker !== undefined) {
        const error = new TaskError(normalized.id, "dependency", 0, blocker);
        this.finish(task, { kind: "cancelled", error });
      } else if (this.dependenciesSucceeded(task)) {
        this.makeReady(task);
      }
    });
  }

  start(): void {
    this.transaction(() => {
      this.started = true;
    });
  }

  pause(): void {
    this.started = false;
  }

  cancel(id: string, reason?: unknown): boolean {
    const task = this.tasks.get(id);
    if (task === undefined || isTerminal(task.phase)) return false;
    this.transaction(() => {
      const previous = task.phase;
      if (previous.kind === "running") this.endAttempt(previous.attempt);
      if (previous.kind === "retrying") this.clock.clearTimeout(previous.timerHandle);
      const error = new TaskError(id, "cancelled", task.attemptsStarted, reason);
      this.finish(task, { kind: "cancelled", error });
      if (previous.kind === "running") previous.attempt.controller.abort(error);
    });
    return true;
  }

  state(id: string): TaskState {
    return this.getTask(id).phase.kind;
  }

  result<T = unknown>(id: string): Promise<T> {
    return this.getTask(id).settlement.promise as Promise<T>;
  }

  onIdle(): Promise<void> {
    if (this.unfinished === 0) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.push(resolve));
  }

  on<E extends keyof SchedulerEvents>(event: E, listener: SchedulerEvents[E]): () => void {
    const subscription: Subscription<E> = { fn: listener };
    const set: Set<Subscription<E>> = this.listeners[event];
    set.add(subscription);
    return () => {
      set.delete(subscription);
    };
  }

  private getTask(id: string): Task {
    const task = this.tasks.get(id);
    if (task === undefined) throw new Error(`unknown task id: ${id}`);
    return task;
  }

  private transaction(body: () => void): void {
    const outermost = this.depth === 0;
    const wasIdle = this.unfinished === 0;
    this.depth++;
    this.moment++;
    try {
      body();
      this.flush();
      if (outermost) this.pump(wasIdle);
    } finally {
      this.depth--;
    }
  }

  private pump(wasIdle: boolean): void {
    for (let idleBefore = wasIdle; ; idleBefore = true) {
      while (this.started && this.running < this.concurrency) {
        const task = this.ready.pop();
        if (task === undefined) break;
        this.startAttempt(task);
      }
      if (this.unfinished > 0) return;
      for (const resolve of this.idleWaiters.splice(0)) resolve();
      if (idleBefore) return;
      this.emit("idle");
      this.flush();
    }
  }

  private emit<E extends keyof SchedulerEvents>(
    event: E,
    ...args: Parameters<SchedulerEvents[E]>
  ): void {
    const set: Set<Subscription<E>> = this.listeners[event];
    this.pendingEvents.push(() => {
      for (const { fn } of [...set]) {
        try {
          (fn as (...a: Parameters<SchedulerEvents[E]>) => void)(...args);
        } catch {}
      }
    });
  }

  private flush(): void {
    if (this.flushing) return;
    this.flushing = true;
    try {
      for (let deliver = this.pendingEvents.shift(); deliver; deliver = this.pendingEvents.shift()) {
        deliver();
      }
    } finally {
      this.flushing = false;
    }
  }

  private makeReady(task: Task): void {
    const phase: QueuedPhase = { kind: "queued", moment: this.moment };
    task.phase = phase;
    this.ready.push({ task, phase });
  }

  private startAttempt(task: Task): void {
    const attempt: Attempt = {
      number: ++task.attemptsStarted,
      controller: new AbortController(),
      timer: undefined,
    };
    task.phase = { kind: "running", attempt };
    this.running++;
    this.emit("start", task.spec.id, attempt.number);
    this.flush();
    if (!this.isCurrent(task, attempt)) return;

    const { timeoutMs } = task.spec;
    if (timeoutMs !== undefined && timeoutMs !== Infinity) {
      const handle = this.clock.setTimeout(
        () => this.transaction(() => this.attemptTimedOut(task, attempt)),
        timeoutMs,
      );
      attempt.timer = { handle };
    }

    const ctx: TaskContext = {
      signal: attempt.controller.signal,
      attempt: attempt.number,
      deps: Object.fromEntries(task.spec.deps.map((dep) => [dep, this.valueOf(dep)])),
    };
    let outcome: Promise<unknown>;
    try {
      outcome = Promise.resolve(task.spec.run(ctx));
    } catch (error) {
      outcome = Promise.reject(error);
    }
    outcome.then(
      (value) => this.transaction(() => this.attemptSucceeded(task, attempt, value)),
      (error: unknown) => this.transaction(() => this.attemptRejected(task, attempt, error)),
    );
  }

  private isCurrent(task: Task, attempt: Attempt): boolean {
    return task.phase.kind === "running" && task.phase.attempt === attempt;
  }

  private endAttempt(attempt: Attempt): void {
    if (attempt.timer !== undefined) this.clock.clearTimeout(attempt.timer.handle);
    attempt.timer = undefined;
    this.running--;
  }

  private attemptSucceeded(task: Task, attempt: Attempt, value: unknown): void {
    if (!this.isCurrent(task, attempt)) return;
    this.endAttempt(attempt);
    this.finish(task, { kind: "succeeded", value });
  }

  private attemptRejected(task: Task, attempt: Attempt, error: unknown): void {
    if (!this.isCurrent(task, attempt)) return;
    this.endAttempt(attempt);
    this.attemptFailed(task, error, new TaskError(task.spec.id, "failed", attempt.number, error));
  }

  private attemptTimedOut(task: Task, attempt: Attempt): void {
    if (!this.isCurrent(task, attempt)) return;
    attempt.timer = undefined;
    this.endAttempt(attempt);
    const error = new TaskError(task.spec.id, "timeout", attempt.number);
    this.attemptFailed(task, error, error);
    attempt.controller.abort(error);
  }

  private attemptFailed(task: Task, attemptError: unknown, finalError: TaskError): void {
    const failed = task.attemptsStarted;
    const { id, retries, backoffMs } = task.spec;
    if (failed > retries) {
      this.finish(task, { kind: "failed", error: finalError });
      return;
    }
    const delayMs = backoffMs * 2 ** (failed - 1);
    if (delayMs > 0) {
      const handle = this.clock.setTimeout(
        () => this.transaction(() => this.backoffElapsed(task, handle)),
        delayMs,
      );
      task.phase = { kind: "retrying", timerHandle: handle };
    }
    this.emit("retry", id, failed + 1, delayMs, attemptError);
    if (delayMs === 0) this.makeReady(task);
  }

  private backoffElapsed(task: Task, handle: unknown): void {
    if (task.phase.kind === "retrying" && task.phase.timerHandle === handle) this.makeReady(task);
  }

  private conclude(task: Task, terminal: TerminalPhase): void {
    task.phase = terminal;
    this.unfinished--;
    if (terminal.kind === "succeeded") task.settlement.resolve(terminal.value);
    else task.settlement.reject(terminal.error);
  }

  private finish(task: Task, terminal: TerminalPhase): void {
    this.conclude(task, terminal);
    const { id } = task.spec;
    switch (terminal.kind) {
      case "succeeded":
        this.emit("success", id, terminal.value);
        this.releaseDependents(id);
        return;
      case "failed":
        this.emit("failure", id, terminal.error);
        this.cascade(id, terminal.error);
        return;
      case "cancelled":
        this.emit("cancel", id, terminal.error);
        this.cascade(id, terminal.error);
        return;
    }
  }

  private releaseDependents(id: string): void {
    for (const dependentId of this.dependentsOf.get(id) ?? []) {
      const dependent = this.tasks.get(dependentId);
      if (dependent?.phase.kind === "waiting" && this.dependenciesSucceeded(dependent)) {
        this.makeReady(dependent);
      }
    }
  }

  private cascade(rootId: string, rootError: TaskError): void {
    const frontier = [{ id: rootId, error: rootError }];
    const victims: Array<{ task: Task; error: TaskError }> = [];
    for (const { id, error } of frontier) {
      for (const dependentId of this.dependentsOf.get(id) ?? []) {
        const dependent = this.tasks.get(dependentId);
        if (dependent?.phase.kind !== "waiting") continue;
        const victimError = new TaskError(dependentId, "dependency", dependent.attemptsStarted, error);
        this.conclude(dependent, { kind: "cancelled", error: victimError });
        victims.push({ task: dependent, error: victimError });
        frontier.push({ id: dependentId, error: victimError });
      }
    }
    victims.sort((a, b) => a.task.order - b.task.order);
    for (const { task, error } of victims) this.emit("cancel", task.spec.id, error);
  }

  private dependenciesSucceeded(task: Task): boolean {
    return task.spec.deps.every((dep) => this.tasks.get(dep)?.phase.kind === "succeeded");
  }

  private firstBrokenDependency(task: Task): TaskError | undefined {
    for (const dep of task.spec.deps) {
      const phase = this.tasks.get(dep)?.phase;
      if (phase?.kind === "failed" || phase?.kind === "cancelled") return phase.error;
    }
    return undefined;
  }

  private valueOf(id: string): unknown {
    const phase = this.tasks.get(id)?.phase;
    return phase?.kind === "succeeded" ? phase.value : undefined;
  }

  private findCycleThrough(id: string, deps: readonly string[]): string[] | undefined {
    const cameFrom = new Map<string, string>();
    const stack: string[] = [];
    for (const dep of deps) {
      if (dep === id) return [id];
      if (!cameFrom.has(dep)) {
        cameFrom.set(dep, id);
        stack.push(dep);
      }
    }
    for (let node = stack.pop(); node !== undefined; node = stack.pop()) {
      for (const dep of this.tasks.get(node)?.spec.deps ?? []) {
        if (dep === id) {
          const path: string[] = [];
          for (let at: string | undefined = node; at !== undefined && at !== id; at = cameFrom.get(at)) {
            path.push(at);
          }
          return [id, ...path.reverse()];
        }
        if (!cameFrom.has(dep)) {
          cameFrom.set(dep, node);
          stack.push(dep);
        }
      }
    }
    return undefined;
  }
}
