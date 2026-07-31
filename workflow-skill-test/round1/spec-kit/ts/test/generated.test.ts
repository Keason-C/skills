/**
 * Drift detection - scenario V27 (task T061).
 *
 * FR-025. This is the test that makes "generated, not hand-written" true rather than
 * aspirational: change a pydantic model, forget to regenerate, and the build fails here
 * instead of at some later point where a field silently vanishes from the TypeScript side.
 */

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { OUTPUT_PATH, SCHEMA_PATH, generate, generateFromDisk } from "../scripts/generate-zod.mjs";

describe("generated zod schema", () => {
  it("matches the committed file byte for byte (V27)", () => {
    const committed = readFileSync(OUTPUT_PATH, "utf8");
    expect(committed).toBe(generateFromDisk());
  });

  it("is deterministic", () => {
    expect(generateFromDisk()).toBe(generateFromDisk());
  });

  it("carries a do-not-edit banner", () => {
    expect(readFileSync(OUTPUT_PATH, "utf8")).toContain("AUTOMATICALLY GENERATED");
  });

  it("emits every enum defined in the JSON Schema", () => {
    const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf8"));
    const output = generateFromDisk();
    for (const [name, def] of Object.entries<Record<string, unknown>>(schema.$defs ?? {})) {
      if (!def.enum) continue;
      for (const member of def.enum as string[]) {
        expect(output, `${name}.${member} missing from generated schema`).toContain(
          JSON.stringify(member),
        );
      }
    }
  });

  it("propagates additionalProperties:false as .strict()", () => {
    expect(generateFromDisk()).toContain(".strict()");
  });

  it("refuses to guess at unsupported schema constructs", () => {
    // Silence on an unknown construct would produce a permissive schema - the exact
    // failure mode a generated contract is supposed to rule out.
    expect(() =>
      generate({ type: "object", properties: { x: { type: "unheard-of" } }, required: ["x"] }),
    ).toThrow(/unsupported/);
  });

  it("rejects an ambiguous multi-branch anyOf", () => {
    expect(() =>
      generate({
        type: "object",
        properties: { x: { anyOf: [{ type: "string" }, { type: "number" }] } },
        required: ["x"],
      }),
    ).toThrow(/anyOf/);
  });

  it("orders definitions so references resolve", () => {
    const output = generateFromDisk();
    // guardFindingSchema references guardRuleSchema, so the latter must come first.
    expect(output.indexOf("guardRuleSchema =")).toBeLessThan(output.indexOf("guardFindingSchema ="));
  });
});
