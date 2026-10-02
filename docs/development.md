# Desarrollo local y verificaciones

Esta guía reúne los comandos operativos del repositorio. `AGENTS.md` y la skill `eventflow-slice` la enlazan para que un agente pueda trabajar y verificar cambios sin usar `README.md` como instrucción.

## Requisitos y arranque del backend

Requiere Python 3.12, `uv` 0.11.16 y Docker Compose. Las credenciales de `compose.yaml` son solo de desarrollo y los puertos se publican en loopback.

```bash
uv sync --locked
docker compose up -d --wait postgres redis
uv run --locked alembic upgrade head
docker compose up -d --build --wait api
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

La API lee `EVENTFLOW_DATABASE_URL` y `EVENTFLOW_REDIS_URL` (véase `.env.example`). Si la base aún no está migrada, la migración también puede ejecutarse dentro de Compose con `docker compose run --rm api uv run --no-dev --locked alembic upgrade head`. `/health/live` indica que el proceso atiende peticiones; `/health/ready` comprueba PostgreSQL y Redis.

## Suite backend completa

Con PostgreSQL y Redis iniciados y la migración aplicada:

```bash
EVENTFLOW_TEST_DATABASE_URL=postgresql+asyncpg://eventflow:eventflow@localhost:5432/eventflow uv run --locked pytest -ra
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
```

La prueba de integración se omite cuando falta `EVENTFLOW_TEST_DATABASE_URL`; un corte no está completamente verificado si aparece ese `skip`. GitHub Actions ejecuta instalación, migración y las mismas comprobaciones con PostgreSQL y Redis. Al añadir frontend u otras suites, actualiza esta guía y CI con sus comandos reales.
