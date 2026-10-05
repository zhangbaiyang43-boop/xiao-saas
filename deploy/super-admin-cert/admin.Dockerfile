# Phase 03R: build the pinned Super Admin candidate inside Docker, never on the host.
# Context is the `git archive` of the candidate commit (see scripts/super-admin-cert.ps1).
# This file and nginx.conf are copied into <context>/_cert/ by the Prepare action.
FROM node:20-alpine AS build

WORKDIR /app

COPY admin-h5/package.json admin-h5/package-lock.json ./
RUN npm ci

COPY admin-h5/ ./

ARG CERT_ADMIN_SHA
ARG VITE_API_BASE_URL=/api
ARG VITE_API_ORIGIN=http://127.0.0.1:28989

ENV ADMIN_RELEASE_SHA=$CERT_ADMIN_SHA
ENV VITE_ADMIN_ENVIRONMENT=super-admin-cert
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_ORIGIN=$VITE_API_ORIGIN

RUN printf '%s' "$CERT_ADMIN_SHA" | grep -Eq '^[0-9a-f]{40}$'
RUN npm run build
# Non-secret traceability beside the artifact; no application code is touched for this.
RUN printf '{"git_sha":"%s","environment":"super-admin-cert","builder":"local-docker-super-admin-cert"}\n' "$CERT_ADMIN_SHA" > dist/build-meta.json

FROM nginx:1.27-alpine

COPY --from=build /app/dist/ /usr/share/nginx/html/
COPY _cert/nginx.conf /etc/nginx/conf.d/default.conf
