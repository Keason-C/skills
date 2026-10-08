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

export class Scheduler {
  constructor(options: SchedulerOptions) {
    throw new Error("not implemented");
  }

  add<T>(spec: TaskSpec<T>): void {
    throw new Error("not implemented");
  }

  start(): void {
    throw new Error("not implemented");
  }

  pause(): void {
    throw new Error("not implemented");
  }

  cancel(id: string, reason?: unknown): boolean {
    throw new Error("not implemented");
  }

  state(id: string): TaskState {
    throw new Error("not implemented");
  }

  result<T = unknown>(id: string): Promise<T> {
    throw new Error("not implemented");
  }

  onIdle(): Promise<void> {
    throw new Error("not implemented");
  }

  on<E extends keyof SchedulerEvents>(event: E, listener: SchedulerEvents[E]): () => void {
    throw new Error("not implemented");
  }
}
