// Differential fuzz harness: random scenarios driven by a fake clock; writes one trace per seed.
// Uses only the public API. Settle/cancel/add times carry unique fractional parts so they never tie
// with scheduler timers (integer offsets), keeping traces implementation-independent.
import { test } from "vitest";
import { writeFileSync } from "node:fs";
import { Scheduler, TaskError, type Clock } from "../src/index.js";

const SEEDS = Number(process.env.FUZZ_SEEDS ?? 300);
const OUT = process.env.FUZZ_OUT ?? "fuzz-traces.json";

function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

class Clk implements Clock {
  t = 0;
  seq = 0;
  timers = new Map<number, { at: number; seq: number; cb: () => void }>();
  now() { return this.t; }
  setTimeout(cb: () => void, ms: number) { const id = ++this.seq; this.timers.set(id, { at: this.t + Math.max(0, ms), seq: id, cb }); return id; }
  clearTimeout(h: unknown) { this.timers.delete(h as number); }
  next() {
    let best: { id: number; at: number; seq: number } | undefined;
    for (const [id, x] of this.timers) if (!best || x.at < best.at || (x.at === best.at && x.seq < best.seq)) best = { id, at: x.at, seq: x.seq };
    return best;
  }
}

const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r)); };

async function scenario(seed: number) {
  const r = rng(seed);
  const pick = <T,>(xs: T[]): T => xs[Math.floor(r() * xs.length)]!;
  const clock = new Clk();
  const s = new Scheduler({ concurrency: 1 + Math.floor(r() * 3), clock });
  const log: unknown[] = [];
  const T = () => Math.round(clock.t * 1000) / 1000;
  const errInfo = (e: unknown) => (e instanceof TaskError ? { kind: e.kind, attempts: e.attempts } : String(e));
  s.on("start", (id, a) => log.push([T(), "start", id, a]));
  s.on("success", (id, v) => log.push([T(), "success", id, v]));
  s.on("retry", (id, n, d) => log.push([T(), "retry", id, n, d]));
  s.on("failure", (id, e) => log.push([T(), "failure", id, errInfo(e)]));
  s.on("cancel", (id, e) => log.push([T(), "cancel", id, errInfo(e)]));
  s.on("idle", () => log.push([T(), "idle"]));
  let frac = 0;
  const uniq = (base: number) => base + (++frac) * 0.001 + 0.0005;
  const n = 3 + Math.floor(r() * 8);
  // DAG: task i may depend on tasks with smaller index; add order is shuffled => forward refs.
  const specs = Array.from({ length: n }, (_, i) => {
    const deps: string[] = [];
    for (let j = 0; j < i; j++) if (r() < 0.25) deps.push(`t${j}`);
    const retries = pick([0, 0, 1, 2]);
    const plan = Array.from({ length: retries + 1 }, () => ({ d: Math.floor(r() * 12) * 10, ok: r() < 0.6 }));
    return { id: `t${i}`, deps, priority: pick([-1, 0, 0, 1, 2]), retries, backoffMs: pick([0, 10, 25, 40]),
      timeoutMs: pick([undefined, undefined, 35, 80]), plan };
  });
  const order = specs.map((_, i) => i).sort(() => r() - 0.5);
  const late = new Set(order.filter(() => r() < 0.2));
  const results: Record<string, unknown> = {};
  const add = (i: number) => {
    const sp = specs[i]!;
    try {
      s.add({ id: sp.id, deps: sp.deps, priority: sp.priority, retries: sp.retries, backoffMs: sp.backoffMs,
        timeoutMs: sp.timeoutMs, run: (ctx) => {
          log.push([T(), "run", sp.id, ctx.attempt, Object.keys(ctx.deps).sort()]);
          const p = sp.plan[ctx.attempt - 1] ?? { d: 5, ok: true };
          return new Promise((res, rej) => {
            clock.setTimeout(() => (p.ok ? res(`${sp.id}#${ctx.attempt}`) : rej(new Error(`${sp.id} fail ${ctx.attempt}`))), uniq(p.d) - 0);
          });
        } });
      s.result(sp.id).then((v) => (results[sp.id] = ["ok", v]), (e) => (results[sp.id] = ["err", errInfo(e)]));
    } catch (e) {
      log.push([T(), "addThrew", sp.id, (e as Error).name]);
    }
  };
  for (const i of order) if (!late.has(i)) add(i);
  for (const i of late) clock.setTimeout(() => add(i), uniq(Math.floor(r() * 10) * 10));
  const cancels = Math.floor(r() * 3);
  for (let k = 0; k < cancels; k++) {
    const id = `t${Math.floor(r() * n)}`;
    clock.setTimeout(() => { try { log.push([T(), "cancelCall", id, s.cancel(id, "c")]); } catch (e) { log.push([T(), "cancelThrew", id]); } }, uniq(Math.floor(r() * 15) * 10));
  }
  if (r() < 0.3) { clock.setTimeout(() => { s.pause(); log.push([T(), "pause"]); }, uniq(20)); clock.setTimeout(() => { s.start(); log.push([T(), "resume"]); }, uniq(60)); }
  s.start();
  await flush();
  for (let guard = 0; guard < 5000; guard++) {
    const nx = clock.next();
    if (!nx) break;
    const x = clock.timers.get(nx.id)!;
    clock.timers.delete(nx.id);
    clock.t = Math.max(clock.t, x.at);
    x.cb();
    await flush();
  }
  await flush();
  const states: Record<string, string> = {};
  for (const sp of specs) { try { states[sp.id] = s.state(sp.id); } catch { states[sp.id] = "unknown"; } }
  return { log, states, results, pendingTimers: clock.timers.size };
}

test("fuzz", async () => {
  let unhandled = 0;
  const h = () => { unhandled++; };
  process.on("unhandledRejection", h);
  const out: Record<number, unknown> = {};
  for (let seed = 1; seed <= SEEDS; seed++) {
    try { out[seed] = await scenario(seed); } catch (e) { out[seed] = { crash: String(e) }; }
  }
  await flush();
  process.off("unhandledRejection", h);
  writeFileSync(OUT, JSON.stringify({ unhandled, traces: out }));
}, 600_000);
