import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // zod ships CommonJS; externalised it is loaded by bare Node, where the named `z` import that
    // src/lib/mentor-chat.functions.ts uses comes back undefined (`z.object is not a function`).
    // Inlining lets Vite's interop produce a real namespace.
    server: { deps: { inline: ["zod"] } },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
