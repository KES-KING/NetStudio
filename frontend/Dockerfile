FROM node:22-bookworm-slim AS dependencies

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:22-bookworm-slim AS builder

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY frontend/ ./
RUN npm run build

FROM node:22-bookworm-slim AS runtime
ARG STOCC_BUILD_REVISION=unknown
ENV STOCC_BUILD_REVISION=${STOCC_BUILD_REVISION}
LABEL org.opencontainers.image.revision=${STOCC_BUILD_REVISION}

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
COPY --chown=node:node LICENSE /app/LICENSE

USER node

EXPOSE 3000

CMD ["node", "server.js"]
