import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    // No network, no servers: these tests read files and validate objects.
    testTimeout: 10_000,
  },
});
