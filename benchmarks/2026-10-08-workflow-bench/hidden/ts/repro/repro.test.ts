// Verification of judge-claimed defects (supplementary). Each test prints PASS/FAIL into a JSON file.
import { test } from "vitest";
import { writeFileSync } from "node:fs";
import { Scheduler, type Clock } from "../src/index.js";

const out: Record<string, string> = {};
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise((r) => setImmediate(r)); };
class Clk implements Clock {
  t = 0; seq = 0; timers = new Map<number, { at: number; cb: () => void }>();
  now() { return this.t; }
  setTimeout(cb: () => void, ms: number) { const id = ++this.seq; this.timers.set(id, { at: this.t + ms, cb }); return id; }
  clearTimeout(h: unknown) { this.timers.delete(h as number); }
  async advance(ms: number) {
    const end = this.t + ms;
    for (;;) {
      let best: [number, { at: number; cb: () => void }] | undefined;
      for (const e of this.timers) if (e[1].at <= end && (!best || e[1].at < best[1].at)) best = e;
      if (!best) break;
      this.timers.delete(best[0]); this.t = best[1].at; best[1].cb(); await flush();
    }
    this.t = end; await flush();
  }
}

async function check(name: string, fn: () => Promise<boolean>) {
  try { out[name] = (await fn()) ? "ok" : "DEFECT"; } catch (e) { out[name] = "DEFECT: " + String(e).slice(0, 120); }
}

test("repro", async () => {
  await check("deep_chain_add_20k_no_stack_overflow", async () => {
    const s = new Scheduler({ concurrency: 1, clock: new Clk() });
    for (let i = 0; i < 20000; i++) s.add({ id: "c" + i, deps: i ? ["c" + (i - 1)] : [], run: async () => i });
    return s.state("c19999") === "waiting";
  });
  await check("cancel_from_abort_listener_on_timeout_emits_no_retry_after_cancel", async () => {
    const clock = new Clk();
    const s = new Scheduler({ concurrency: 1, clock });
    const ev: string[] = [];
    s.on("retry", (id) => ev.push("retry:" + id)); s.on("cancel", (id) => ev.push("cancel:" + id));
    s.on("start", (id, a) => ev.push(`start:${id}:${a}`));
    s.add({ id: "a", retries: 2, backoffMs: 5, timeoutMs: 10, run: (ctx) => {
      ctx.signal.addEventListener("abort", () => { s.cancel("a"); });
      return new Promise(() => {});
    } });
    s.start(); await flush(); await clock.advance(100);
    const ci = ev.indexOf("cancel:a");
    return ci >= 0 && !ev.slice(ci).some((e) => e.startsWith("retry") || e.startsWith("start")) && s.state("a") === "cancelled" && clock.timers.size === 0;
  });
  await check("cancel_inside_start_listener_does_not_run", async () => {
    const s = new Scheduler({ concurrency: 1, clock: new Clk() });
    let ran = false;
    s.on("start", (id) => { s.cancel(id); });
    s.add({ id: "a", run: async () => { ran = true; } });
    s.start(); await flush();
    return s.state("a") === "cancelled";
  });
  await check("duplicate_listener_unsubscribe_independent", async () => {
    const s = new Scheduler({ concurrency: 1, clock: new Clk() });
    let n = 0; const l = () => { n++; };
    const u1 = s.on("start", l); const u2 = s.on("start", l); u2();
    s.add({ id: "a", run: async () => 1 }); s.start(); await flush(); u1();
    return n === 1;
  });
  writeFileSync(process.env.REPRO_OUT ?? "repro.json", JSON.stringify(out));
}, 600000);
