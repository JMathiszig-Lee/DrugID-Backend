# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=24.18.0
ARG PYTHON_VERSION=3.14.6
ARG UV_VERSION=0.11.28

FROM node:${NODE_VERSION}-bookworm-slim AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY frontend/ ./
RUN npm run build


FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin


FROM python:${PYTHON_VERSION}-slim-bookworm AS python-dependencies

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY --from=uv-bin /uv /uvx /bin/
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM python-dependencies AS analysis-dependencies

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group analysis --no-install-project


FROM python:${PYTHON_VERSION}-slim-bookworm AS analysis

ENV PATH=/app/.venv/bin:$PATH \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /home/app \
        --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=analysis-dependencies --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app analysis ./analysis
COPY --chown=app:app uv.lock ./uv.lock

USER app

ENTRYPOINT ["python", "-m", "analysis.ampoule_analysis"]
CMD ["--help"]


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV DJANGO_SETTINGS_MODULE=DrugID.settings \
    PATH=/app/.venv/bin:$PATH \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /home/app \
        --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=python-dependencies --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app manage.py ./
COPY --chown=app:app DrugID ./DrugID
COPY --chown=app:app DrugID_API ./DrugID_API
COPY --chown=app:app --chmod=755 docker ./docker
COPY --from=frontend-build --chown=app:app /build/frontend/dist ./frontend/dist

RUN test -f /app/DrugID_API/study_assets/industry/adrenaline.png

RUN mkdir -p /app/staticfiles \
    && chown app:app /app/staticfiles

USER app

RUN SECRET_KEY=collectstatic-build-only-key-DO-NOT-USE-at-runtime-0123456789abcdef \
    DEBUG=False \
    ALLOWED_HOSTS=localhost \
    PUBLIC_APP_URL=http://localhost \
    DATABASE_URL=sqlite:////tmp/drugid-collectstatic.sqlite3 \
    EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/docker/gunicorn.conf.py", "DrugID.wsgi:application"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]
