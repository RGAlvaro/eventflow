# Desarrollo local y verificaciones

Esta guía reúne los comandos operativos del repositorio. `AGENTS.md` y la skill `eventflow-slice` la enlazan para que un agente pueda trabajar y verificar cambios sin usar `README.md` como instrucción.

## Requisitos y arranque del backend

Requiere Python 3.12, `uv` 0.11.16 y Docker Compose. Las credenciales de `compose.yaml` son solo de desarrollo y los puertos se publican en loopback.

Antes de migrar o arrancar servicios, copia `.env.example` a `.env` y sustituye el valor de `EVENTFLOW_ENCRYPTION_KEYS` por un objeto JSON con una clave propia de 32 bytes codificada en base64. Para generar el valor del objeto sin reutilizar una clave de otro entorno:

```bash
python3 -c 'import base64,json,secrets; print(json.dumps({"dev":base64.b64encode(secrets.token_bytes(32)).decode()}))'
```

Mantén `EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID=dev`. La API y el worker necesitan el mismo conjunto de claves; Compose toma esas variables de `.env`. Si ya existen endpoints, conserva la clave al actualizar o restaurar la base: la migración 0004 cifra sus secretos y detiene la operación si no puede leer la clave. `.env` está excluido de Git.

```bash
uv sync --locked
docker compose up -d --wait postgres redis
uv run --locked alembic upgrade head
docker compose up -d --build --wait api worker dispatcher
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

La API lee `EVENTFLOW_DATABASE_URL`, `EVENTFLOW_REDIS_URL` y la clave de cifrado (véase `.env.example`). Si la base aún no está migrada, la migración también puede ejecutarse dentro de Compose con `docker compose run --rm api alembic upgrade head`. `/health/live` indica que el proceso atiende peticiones; `/health/ready` comprueba PostgreSQL y Redis.

El despachador consulta cada 10 s el outbox y las entregas pendientes o con lease vencido en PostgreSQL; Celery consume los avisos desde Redis. El worker limita a cuatro tareas en el contenedor y la base limita a cuatro entregas HTTP activas entre todos los workers. Para observarlos: `docker compose logs -f dispatcher worker`. Las filas de endpoint y las claves se crean con fixtures por ahora; no hay API de configuración pública. El receptor HTTP de loopback solo se habilita con `EVENTFLOW_ENVIRONMENT=test` (o `development`) y `EVENTFLOW_LOCAL_TEST_RECEIVER_URL` igual a la URL exacta del receptor.

En el hito 2, un replay se solicita solo mediante el comando interno `uv run --locked python -m eventflow.replay <delivery-uuid>`. El comando pide la clave de gestión sin mostrarla en los argumentos del proceso y acepta únicamente una entrega `dead_lettered` de su organización. La clave de gestión sigue viniendo de una fixture: aún no hay API pública para emitirla.

## Suite backend completa

Con PostgreSQL y Redis iniciados y la migración aplicada:

```bash
docker compose stop worker dispatcher
```

Esto evita que los servicios locales consuman las filas temporales de la suite; las pruebas de entrega arrancan su propio proceso Celery contra Redis.

```bash
EVENTFLOW_TEST_DATABASE_URL=postgresql+asyncpg://eventflow:eventflow@localhost:5432/eventflow uv run --locked pytest -ra
uv run --locked alembic check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
```

Las pruebas de integración se omiten cuando falta `EVENTFLOW_TEST_DATABASE_URL`; un corte no está completamente verificado si aparece algún `skip`. GitHub Actions ejecuta instalación, migración y las mismas comprobaciones con PostgreSQL y Redis. Al añadir frontend u otras suites, actualiza esta guía y CI con sus comandos reales.
