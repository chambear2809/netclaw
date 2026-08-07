# Build the browser bundle separately from the small Node runtime that serves
# the HUD API and proxies chat to the in-cluster OpenClaw gateway.
FROM node:22-bookworm-slim AS build

WORKDIR /build
COPY ui/netclaw-visual/package.json ui/netclaw-visual/package-lock.json ./
RUN npm ci
COPY ui/netclaw-visual/ ./
# In the source tree this is a symlink outside the UI directory. Materialise
# the fixture data inside the image so Vite has a self-contained public tree.
RUN rm -f public/fixtures
COPY specs/072-hud-2-org-chart/fixtures/ ./public/fixtures/
RUN npm run build

FROM node:22-bookworm-slim

WORKDIR /opt/netclaw-ui
COPY ui/netclaw-visual/package.json ui/netclaw-visual/package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /build/dist ./dist
COPY ui/netclaw-visual/server.js ./server.js
COPY ui/netclaw-visual/src/telemetry/chat-telemetry.js ./src/telemetry/chat-telemetry.js

# The public HUD needs visual metadata only. It deliberately excludes .env,
# OpenClaw session transcripts, credential-bearing MCP configuration, and the
# device testbed. Public mode disables all testbed routes, so copying it would
# only broaden the impact of a container compromise.
COPY --chown=node:node workspace /opt/netclaw/workspace
COPY --chown=node:node deploy/kubernetes/openclaw.json /opt/netclaw/config/openclaw.json
COPY --chown=node:node IDENTITY.md SOUL.md /opt/netclaw/

USER node
ENV NODE_ENV=production \
    NETCLAW_ROOT=/opt/netclaw \
    HUD_PORT=3001
EXPOSE 3001
CMD ["node", "server.js"]
