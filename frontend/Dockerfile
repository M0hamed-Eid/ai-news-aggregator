# STALE / NOT CURRENTLY USED — the frontend now deploys to Vercel instead
# (project decision after the Oracle Cloud VM path had no free-tier
# capacity available). next.config.ts's `output: "standalone"` and
# package.json's standalone-copying build/start scripts were both removed
# since Vercel needs the default Next.js build output, not a standalone
# server bundle -- this Dockerfile depends on exactly that removed output
# and will fail at the `COPY --from=builder /app/.next/standalone` step
# unless both are restored first. Left in place (not deleted) in case a
# self-hosted Docker path is ever wanted again alongside AWS backend
# hosting; do not build this image as-is.
#
# Next.js frontend image — deliberately separate from web/Dockerfile (own
# runtime, own dependency set), same convention as this project's other
# per-service images.

FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
# `npm ci` fails here on a real quirk, not a bug in this lockfile: sharp's
# optional per-platform native deps resolve slightly differently between
# the npm version that wrote package-lock.json (Windows, local dev) and
# the one bundled in node:22-alpine, which trips npm ci's strict "lockfile
# must match exactly" check. `npm install` tolerates that drift while still
# resolving from the same lockfile/version pins.
RUN npm install
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./

EXPOSE 3000

CMD ["node", "server.js"]
