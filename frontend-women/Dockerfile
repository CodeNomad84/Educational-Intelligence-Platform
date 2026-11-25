# frontend-women — girls' app image (ADR-0014 two JSON frontends, ADR-0015 containers + edge gateway).
#   deps    : bun installs from the committed lockfile (never `npm install`, there is no package-lock.json)
#   build   : JS gate (D6) — lint + typecheck + unit tests, then the nitro `node-server` build
#   runtime : plain Node, no bun, no source tree, non-root `node` user, no host port (the gateway reaches it)
FROM oven/bun:1-alpine AS deps
WORKDIR /app
# Manifests first so the dependency layer is reused across source edits.
COPY package.json bun.lock bunfig.toml ./
RUN bun install --frozen-lockfile

FROM deps AS build
# VPS is 2 vCPU / 4 GB: cap the Node heap so the nitro/vite build never OOMs the host.
ENV NODE_OPTIONS=--max-old-space-size=1024
COPY . .
# D6: a lint/type/test failure fails the image, so a broken frontend cannot be deployed.
RUN bun run lint && bunx tsc --noEmit && bun run test && bun run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOST=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/" >/dev/null || exit 1
CMD ["node", ".output/server/index.mjs"]
