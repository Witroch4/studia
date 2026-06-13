# ---- Dependencies ----
FROM node:24-alpine AS deps
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# ---- Build ----
FROM node:24-alpine AS build
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* é inlinado no bundle do cliente em build-time. Em produção o
# frontend chama a API no mesmo domínio (Traefik roteia /api → backend).
ARG NEXT_PUBLIC_API_URL=https://studia.witdev.com.br
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# "1" liga o botão "Continuar com Google" no /login e /cadastro. build.sh deriva
# automaticamente de GOOGLE_CLIENT_ID presente no .env local.
ARG NEXT_PUBLIC_GOOGLE_AUTH=
ENV NEXT_PUBLIC_GOOGLE_AUTH=$NEXT_PUBLIC_GOOGLE_AUTH
RUN pnpm run build

# ---- Production ----
FROM node:24-alpine AS production
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
WORKDIR /app

COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
