# ── Stage 1: build React UI ───────────────────────────────────────────────────
FROM node:20-alpine AS ui-builder
WORKDIR /ui
COPY packages/ui/package*.json ./
RUN npm ci
COPY packages/ui/ ./
RUN npm run build

# ── Stage 2: Python API + MCP server ──────────────────────────────────────────
FROM python:3.11-slim AS api
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace manifest + lock first (cached layer — only re-runs if deps change)
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml ./packages/core/pyproject.toml

# Install all runtime deps into .venv (no test/dev deps)
RUN uv sync --frozen --no-dev

# Copy application source
COPY packages/core/src/ ./packages/core/src/

# Slate DB lives here (mounted as a volume in compose)
RUN mkdir -p /root/.slate
VOLUME /root/.slate

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "slate.api.app:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000"]

# ── Stage 3: nginx serving the React SPA ──────────────────────────────────────
FROM nginx:alpine AS ui
COPY --from=ui-builder /ui/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
