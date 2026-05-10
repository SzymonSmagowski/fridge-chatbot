# Multi-stage Next.js 16 production build using `output: 'standalone'`.
# Final image is ~200 MB (vs ~800 MB+ for a "ship the full node_modules" build)
# because Next.js traces only the files actually imported and copies them into
# .next/standalone/. Run with `node server.js` — `next start` does NOT work
# with standalone (Next.js 16 warns and refuses).

FROM node:24-alpine AS deps
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:24-alpine AS builder
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate \
    && apk add --no-cache bash curl
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Wake-word ONNX models — fetched at build time so the image is self-contained.
RUN bash scripts/download-wake-word-models.sh
# Produces .next/standalone/ + .next/static/ when next.config.ts has output: 'standalone'.
RUN pnpm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -g 1001 -S nextjs \
    && adduser -S -u 1001 -G nextjs nextjs

# Standalone output bundles a minimal server.js + only-needed-node_modules at .next/standalone/.
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
# Static assets (CSS chunks, images, etc.) — NOT included in standalone, must be copied separately.
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static
# Public folder (favicons, wake-word ONNX, etc.) — also not in standalone.
COPY --from=builder --chown=nextjs:nextjs /app/public ./public

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
