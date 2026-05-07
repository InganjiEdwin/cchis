import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
  },
  resolve: {
    alias: [
      { find: /^@\//, replacement: `${rootDir}/` },
      { find: /^server-only$/, replacement: `${rootDir}/test/server-only.ts` },
    ],
  },
});
