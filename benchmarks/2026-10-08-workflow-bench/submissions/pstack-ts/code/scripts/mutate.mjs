import { readFileSync, writeFileSync } from "node:fs";
import { execSync } from "node:child_process";

const file = new URL("../src/index.ts", import.meta.url);
const original = readFileSync(file, "utf8");

const mutations = [
  ["priority order reversed", "return a.task.spec.priority > b.task.spec.priority;", "return a.task.spec.priority < b.task.spec.priority;"],
  ["moment ignored", "if (a.phase.moment !== b.phase.moment) return a.phase.moment < b.phase.moment;", ""],
  ["add-order tiebreak reversed", "return a.task.order < b.task.order;", "return a.task.order > b.task.order;"],
  ["linear backoff", "backoffMs * 2 ** (failed - 1)", "backoffMs * failed"],
  ["timeout timer not cleared", "if (attempt.timer !== undefined) this.clock.clearTimeout(attempt.timer.handle);", ""],
  ["backoff timer not cleared on cancel", "if (previous.kind === \"retrying\") this.clock.clearTimeout(previous.timerHandle);", ""],
  ["stale settle not ignored", "if (!this.isCurrent(task, attempt)) return;\n    this.endAttempt(attempt);\n    this.finish(task, { kind: \"succeeded\", value });", "this.endAttempt(attempt);\n    this.finish(task, { kind: \"succeeded\", value });"],
  ["signal not aborted on cancel", "if (previous.kind === \"running\") previous.attempt.controller.abort(error);", ""],
  ["cascade in discovery order", "victims.sort((a, b) => a.task.order - b.task.order);", ""],
  ["cascade cause is root", "frontier.push({ id: dependentId, error: victimError });", "frontier.push({ id: dependentId, error: rootError });"],
  ["idle fires even when idle before", "if (idleBefore) return;", ""],
  ["one retry too many", "if (failed > retries) {", "if (failed > retries + 1) {"],
  ["zero delay uses a timer", "if (delayMs > 0) {", "if (delayMs >= 0) {"],
  ["start listener cancel ignored", "if (!this.isCurrent(task, attempt)) return;\n\n    const { timeoutMs }", "const { timeoutMs }"],
  ["no unhandled guard", "promise.catch(() => {});", ""],
  ["dependency-failed check skipped in add", "if (blocker !== undefined) {", "if (false as boolean) {"],
  ["cycle check skipped", "if (cycle !== undefined) throw new CycleError(cycle);", ""],
  ["dispatch ignores pause", "while (this.started && this.running < this.concurrency) {", "while (this.running < this.concurrency) {"],
];

const survivors = [];
try {
  for (const [name, from, to] of mutations) {
    if (!original.includes(from)) throw new Error(`mutation anchor missing: ${name}`);
    writeFileSync(file, original.replace(from, to));
    let caught = false;
    try {
      execSync("npx vitest run", { stdio: "pipe", timeout: 60_000 });
    } catch {
      caught = true;
    }
    console.log(`${caught ? "caught  " : "SURVIVED"} ${name}`);
    if (!caught) survivors.push(name);
  }
} finally {
  writeFileSync(file, original);
}
process.exitCode = survivors.length === 0 ? 0 : 1;
