# Next.js frontend image — deliberately separate from web/Dockerfile (own
# runtime, own dependency set), same convention as this project's other
# per-service images. Multi-stage: the builder installs full node_modules
# and runs `next build` (output: "standalone", next.config.ts); the runner
# only ships the trimmed standalone bundle package.json's own build script
# already copies .next/static + public/ into (see package.json).

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
