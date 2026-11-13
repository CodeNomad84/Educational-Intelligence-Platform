// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// Never set ssr.external or resolve.external: the Worker has no runtime module resolution, so
// the build fails. Never add compression (compressPublicAssets, vite-plugin-compression):
// hosting already compresses at the edge.
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  // ADR-0015 (2026-11-13): the wrapper defaults nitro to `cloudflare-module`, which emits a Workers
  // bundle, not a runnable server. The container runs the app as plain Node (`.output/server/index.mjs`,
  // port 3000), so the preset is overridden here. `bun run dev` (5173 + /api proxy) is unaffected.
  nitro: { preset: "node-server" },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  // Local dev integration with the Django API (ADR-0014, docs/changes/0040 §18.1): this app owns 5173 and forwards
  // /api to Django, so the browser sees ONE origin and the session cookie + CSRF token need no CORS entry.
  // The dev server only: `vite preview` and the Worker build never proxy anything.
  vite: {
    server: {
      port: 5173,
      strictPort: true, // fail loudly instead of drifting to 5174 and colliding with the other frontend
      proxy: {
        // Default keeps the host workflow (`bun run dev` → 127.0.0.1:8000); the optional
        // `frontends-dev` compose profile sets VITE_DEV_API_TARGET=http://django:8000 (ADR-0015 D3).
        "/api": {
          target: process.env["VITE_DEV_API_TARGET"] ?? "http://127.0.0.1:8000",
          changeOrigin: false,
        },
      },
    },
  },
});
