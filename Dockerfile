# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY webapp/package.json webapp/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --strict-ssl=true
COPY webapp/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock ./backend/requirements.lock
RUN --mount=type=secret,id=ca_bundle \
    if [ -s /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    pip install --no-cache-dir --require-hashes -r backend/requirements.lock
COPY --chown=10001:10001 backend/app ./backend/app
COPY --chown=10001:10001 backend/migrations ./backend/migrations
COPY --chown=10001:10001 backend/alembic.ini ./backend/alembic.ini
COPY --from=frontend --chown=10001:10001 /build/dist ./webapp/dist
RUN groupadd --gid 10001 mapauto && useradd --uid 10001 --gid mapauto --no-create-home mapauto
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8000","--no-access-log","--no-proxy-headers"]
