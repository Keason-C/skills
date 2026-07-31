/**
 * Generate a zod schema from the JSON Schema that pydantic emits (task T056, research R3).
 *
 * Why generate rather than hand-write?  FR-025 requires the published contract to come from
 * the same definitions Python validates against, and FR-028 forbids this side re-deriving
 * anything.  A hand-written zod schema is a second source of truth: it can drift silently,
 * and a newly added Python field simply never appears here.  Generation makes that
 * impossible, and `test/generated.test.ts` fails the build if the committed output is stale.
 *
 * Why our own generator rather than a codegen package?  We control the input.  The schema
 * pydantic produces for these models uses a small, closed subset: object / string / number /
 * integer / boolean / array, `enum` via `$defs` + `$ref`, `anyOf` with null for optionals,
 * plus `required` and `additionalProperties: false`.  A general JSON Schema compiler would
 * be a dependency we would still have to test, on a project whose whole thesis is
 * auditability.  Anything outside the supported subset throws rather than being guessed at.
 *
 *   node scripts/generate-zod.mjs [--check]
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const SCHEMA_PATH = resolve(HERE, "../../schema/triage_result.schema.json");
export const OUTPUT_PATH = resolve(HERE, "../src/schema.generated.ts");

const ROOT_NAME = "TriageResult";

/** Turn a `$ref` like `#/$defs/GuardRule` into `GuardRule`. */
function refName(ref) {
  const match = /^#\/\$defs\/(.+)$/.exec(ref);
  if (!match) throw new Error(`unsupported $ref: ${ref}`);
  return match[1];
}

/** `GuardFinding` -> `guardFindingSchema` */
function schemaConst(name) {
  return `${name[0].toLowerCase()}${name.slice(1)}Schema`;
}

/**
 * Compile one JSON Schema node to a zod expression.
 * Throws on anything outside the supported subset - silence would defeat the purpose.
 */
function compile(node, path) {
  if (node.$ref) return schemaConst(refName(node.$ref));

  // Optionals arrive as anyOf: [<type>, {type: "null"}].
  if (node.anyOf) {
    const nonNull = node.anyOf.filter((entry) => entry.type !== "null");
    const nullable = node.anyOf.length !== nonNull.length;
    if (nonNull.length !== 1) {
      throw new Error(`unsupported anyOf with ${nonNull.length} non-null branches at ${path}`);
    }
    const inner = compile(nonNull[0], path);
    return nullable ? `${inner}.nullable()` : inner;
  }

  if (node.enum) {
    const members = node.enum.map((value) => JSON.stringify(value)).join(", ");
    return `z.enum([${members}])`;
  }

  switch (node.type) {
    case "string": {
      let expr = "z.string()";
      if (node.minLength !== undefined) expr += `.min(${node.minLength})`;
      if (node.maxLength !== undefined) expr += `.max(${node.maxLength})`;
      return expr;
    }
    case "integer": {
      let expr = "z.number().int()";
      if (node.minimum !== undefined) expr += `.min(${node.minimum})`;
      if (node.maximum !== undefined) expr += `.max(${node.maximum})`;
      return expr;
    }
    case "number": {
      let expr = "z.number()";
      if (node.minimum !== undefined) expr += `.min(${node.minimum})`;
      if (node.maximum !== undefined) expr += `.max(${node.maximum})`;
      return expr;
    }
    case "boolean":
      return "z.boolean()";
    case "array": {
      if (!node.items) throw new Error(`array without items at ${path}`);
      let expr = `z.array(${compile(node.items, `${path}.items`)})`;
      if (node.minItems !== undefined) expr += `.min(${node.minItems})`;
      if (node.maxItems !== undefined) expr += `.max(${node.maxItems})`;
      return expr;
    }
    case "object":
      return compileObject(node, path);
    default:
      throw new Error(`unsupported schema node at ${path}: ${JSON.stringify(node)}`);
  }
}

function compileObject(node, path) {
  const required = new Set(node.required ?? []);
  const properties = node.properties ?? {};
  const lines = Object.keys(properties)
    .sort()
    .map((key) => {
      let expr = compile(properties[key], `${path}.${key}`);
      if (!required.has(key)) {
        // A pydantic field with a default is optional on the wire but always present on a
        // value we produce; `.optional()` accepts both.
        expr += ".optional()";
      }
      return `  ${JSON.stringify(key)}: ${expr},`;
    });

  const body = `z.object({\n${lines.join("\n")}\n})`;
  // `additionalProperties: false` is how `extra="forbid"` crosses the language boundary.
  return node.additionalProperties === false ? `${body}.strict()` : body;
}

/** Order `$defs` so a definition is emitted after everything it references. */
function orderDefs(defs) {
  const ordered = [];
  const seen = new Set();

  const visit = (name, stack) => {
    if (seen.has(name)) return;
    if (stack.has(name)) throw new Error(`circular $ref involving ${name}`);
    stack.add(name);
    for (const dep of collectRefs(defs[name])) visit(dep, stack);
    stack.delete(name);
    seen.add(name);
    ordered.push(name);
  };

  for (const name of Object.keys(defs).sort()) visit(name, new Set());
  return ordered;
}

function collectRefs(node, found = []) {
  if (node === null || typeof node !== "object") return found;
  if (Array.isArray(node)) {
    for (const entry of node) collectRefs(entry, found);
    return found;
  }
  if (typeof node.$ref === "string") found.push(refName(node.$ref));
  for (const [key, value] of Object.entries(node)) {
    if (key !== "$ref") collectRefs(value, found);
  }
  return found;
}

/** Build the full TypeScript module text. Deterministic: same input, same bytes. */
export function generate(schema) {
  const defs = schema.$defs ?? {};
  const chunks = [];

  chunks.push(
    "// AUTOMATICALLY GENERATED - DO NOT EDIT.",
    "//",
    "// Source:    schema/triage_result.schema.json (itself generated from the pydantic models)",
    "// Generator: ts/scripts/generate-zod.mjs",
    "// Regenerate: npm run gen",
    "//",
    "// Editing this file by hand would recreate the second-source-of-truth problem the",
    "// generator exists to prevent. test/generated.test.ts fails the build if it is stale.",
    "",
    'import { z } from "zod";',
    "",
  );

  for (const name of orderDefs(defs)) {
    const node = defs[name];
    chunks.push(
      `export const ${schemaConst(name)} = ${compile(node, name)};`,
      `export type ${name} = z.infer<typeof ${schemaConst(name)}>;`,
      "",
    );
  }

  chunks.push(
    `export const ${schemaConst(ROOT_NAME)} = ${compile(schema, ROOT_NAME)};`,
    `export type ${ROOT_NAME} = z.infer<typeof ${schemaConst(ROOT_NAME)}>;`,
    "",
  );

  return chunks.join("\n");
}

export function generateFromDisk() {
  return generate(JSON.parse(readFileSync(SCHEMA_PATH, "utf8")));
}

const invokedDirectly =
  process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));

if (invokedDirectly) {
  const output = generateFromDisk();
  if (process.argv.includes("--check")) {
    const current = readFileSync(OUTPUT_PATH, "utf8");
    if (current !== output) {
      console.error("schema.generated.ts is stale - run: npm run gen");
      process.exit(1);
    }
    console.log("schema.generated.ts is up to date");
  } else {
    writeFileSync(OUTPUT_PATH, output, "utf8");
    console.log(`wrote ${OUTPUT_PATH}`);
  }
}
