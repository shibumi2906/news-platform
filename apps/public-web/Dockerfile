FROM node:24-alpine AS dependencies
WORKDIR /app
COPY apps/public-web/package.json apps/public-web/package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY apps/public-web ./
ARG NEXT_PUBLIC_SITE_NAME="Signal Desk"
ARG NEXT_PUBLIC_WEB_URL="http://localhost:3000"
ARG NEXT_PUBLIC_PORTAL_THEME="editorial"
ENV NEXT_PUBLIC_SITE_NAME=$NEXT_PUBLIC_SITE_NAME
ENV NEXT_PUBLIC_WEB_URL=$NEXT_PUBLIC_WEB_URL
ENV NEXT_PUBLIC_PORTAL_THEME=$NEXT_PUBLIC_PORTAL_THEME
ENV SITE_API_URL=http://site-api:8000
ENV INTEGRATOR_API_URL=http://integrator-api:8000
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
RUN addgroup -S web && adduser -S web -G web
COPY --from=builder --chown=web:web /app/.next/standalone ./
COPY --from=builder --chown=web:web /app/.next/static ./.next/static
USER web
EXPOSE 3000
CMD ["node", "server.js"]
