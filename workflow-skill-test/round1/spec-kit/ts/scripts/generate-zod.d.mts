/**
 * Types for the zod generator.
 *
 * The generator itself is plain ESM JavaScript -- it runs as a build step before any
 * TypeScript exists, so it cannot depend on the TypeScript toolchain. This declaration lets
 * `test/generated.test.ts` import it under `strict` without weakening `allowJs`/`noImplicitAny`
 * for the whole package.
 */

/** Absolute path to the pydantic-generated JSON Schema this generator consumes. */
export declare const SCHEMA_PATH: string;

/** Absolute path to the generated zod module. */
export declare const OUTPUT_PATH: string;

/**
 * Compile a JSON Schema document into TypeScript source defining zod schemas.
 * Throws on any construct outside the supported subset rather than guessing.
 */
export declare function generate(schema: unknown): string;

/** Convenience wrapper: read {@link SCHEMA_PATH} and {@link generate} it. */
export declare function generateFromDisk(): string;
