FROM node:20-alpine AS build

WORKDIR /app

COPY admin-h5/package.json admin-h5/package-lock.json ./
RUN npm ci

COPY admin-h5/ ./

ARG ADMIN_RELEASE_SHA
ARG VITE_ADMIN_ENVIRONMENT=staging
ARG VITE_API_BASE_URL=/api
ARG VITE_API_ORIGIN=http://127.0.0.1:18989

ENV ADMIN_RELEASE_SHA=$ADMIN_RELEASE_SHA
ENV VITE_ADMIN_ENVIRONMENT=$VITE_ADMIN_ENVIRONMENT
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_ORIGIN=$VITE_API_ORIGIN

RUN printf '%s' "$ADMIN_RELEASE_SHA" | grep -Eq '^[0-9a-f]{40}$'
RUN npm run build
RUN printf '{"sha":"%s","environment":"staging","builder":"local-docker-performance-staging"}\n' "$ADMIN_RELEASE_SHA" > dist/release.json

FROM nginx:1.27-alpine

COPY --from=build /app/dist/ /usr/share/nginx/html/
COPY deploy/performance-staging/nginx.conf /etc/nginx/conf.d/default.conf
