# syntax=docker/dockerfile:1
# One image runs everything: the web UI and API, and the scheduler (the launchd jobs). Only the runtime dependencies are installed:
# the heavy research group (torch, lightgbm) stays out, so the image is small and nothing in it can train or download models.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH GETRICH_HOME=/app GETRICH_DATA=/data GETRICH_NOTIFY=0 TZ=Asia/Colombo
RUN pip install --no-cache-dir uv==0.9.5 || pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-default-groups
COPY --from=web /web/dist /app/frontend_dist
RUN mkdir -p /data /app/config /app/docs /app/research
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=8s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/jobs', timeout=6).status == 200 else 1)"
ENTRYPOINT ["getrich"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
