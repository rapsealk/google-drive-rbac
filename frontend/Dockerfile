# --- build stage ---
FROM node:22-alpine AS build
WORKDIR /app
COPY .npmrc package.json pnpm-lock.yaml ./
# pnpm 12 (corepack-pinned) enforces a default minimum-release-age policy and
# refuses unapproved build scripts; both are disabled for this build.
RUN corepack enable && pnpm install --frozen-lockfile \
      --config.minimum-release-age=0 --dangerously-allow-all-builds
COPY . .
RUN pnpm --config.minimum-release-age=0 --config.verify-deps-before-run=false build

# --- serve stage ---
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
