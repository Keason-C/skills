// Supplementary scalability probe (not part of the brief's acceptance score). Reports wall time per scenario.
import { test } from "vitest";
import { writeFileSync } from "node:fs";
import { Scheduler, type Clock } from "../src/index.js";

const clock: Clock = { now: () => 0, setTimeout: () => 0, clearTimeout: () => {} };
const flush = async () => { for (let i = 0; i < 3; i++) await new Promise((r) => setImmediate(r)); };
const out: Record<string, number | string> = {};

async function timed(name: string, fn: () => Promise<void>, budgetMs: number) {
  if (process.env.SCALE_ONLY && process.env.SCALE_ONLY !== name) return;
  const t0 = performance.now();
  try {
    await Promise.race([fn(), new Promise((_, rej) => setTimeout(() => rej(new Error("over budget")), budgetMs))]);
    out[name] = Math.round(performance.now() - t0);
  } catch (e) { out[name] = "TIMEOUT>" + budgetMs; }
}

test("scale", async () => {
  await timed("independent_20k_c4", async () => {
    const s = new Scheduler({ concurrency: 4, clock });
    for (let i = 0; i < 20000; i++) s.add({ id: "t" + i, priority: i % 7, run: async () => i });
    s.start(); await s.onIdle();
  }, 30000);
  await timed("chain_5k", async () => {
    const s = new Scheduler({ concurrency: 2, clock });
    for (let i = 0; i < 5000; i++) s.add({ id: "c" + i, deps: i ? ["c" + (i - 1)] : [], run: async () => i });
    s.start(); await s.onIdle();
  }, 30000);
  await timed("chain_5k_reverse_add", async () => {
    const s = new Scheduler({ concurrency: 2, clock });
    for (let i = 4999; i >= 0; i--) s.add({ id: "c" + i, deps: i ? ["c" + (i - 1)] : [], run: async () => i });
    s.start(); await s.onIdle();
  }, 30000);
  await timed("fanout_1_to_10k_fail_cascade", async () => {
    const s = new Scheduler({ concurrency: 8, clock });
    s.add({ id: "root", run: async () => { throw new Error("x"); } });
    for (let i = 0; i < 10000; i++) s.add({ id: "f" + i, deps: ["root"], run: async () => i });
    s.start(); await s.onIdle();
  }, 30000);
  await timed("diamond_layers_200x20", async () => {
    const s = new Scheduler({ concurrency: 8, clock });
    for (let l = 0; l < 200; l++) for (let k = 0; k < 20; k++)
      s.add({ id: `d${l}_${k}`, deps: l ? Array.from({ length: 20 }, (_, j) => `d${l - 1}_${j}`) : [], run: async () => 1 });
    s.start(); await s.onIdle();
  }, 30000);
  await flush();
  writeFileSync(process.env.SCALE_OUT ?? "scale.json", JSON.stringify(out));
}, 300000);
