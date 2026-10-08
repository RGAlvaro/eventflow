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

El despachador consulta cada 10 s el outbox y las entregas pendientes o con lease vencido en PostgreSQL; Celery consume los avisos desde Redis. El worker limita a cuatro tareas en el contenedor y la base limita a cuatro entregas HTTP activas entre todos los workers. Para observarlos: `docker compose logs -f dispatcher worker`. El receptor HTTP de loopback solo se habilita con `EVENTFLOW_ENVIRONMENT=test` (o `development`) y `EVENTFLOW_LOCAL_TEST_RECEIVER_URL` igual a la URL exacta del receptor.

## Aprovisionamiento y rotación de credenciales

Con la migración aplicada y acceso al entorno del servidor, el operador crea una organización y su primera credencial `manage`:

```bash
uv run --locked python -m eventflow.bootstrap "Nombre de la organización"
```

El comando imprime el UUID y la clave de gestión **una sola vez**. Entrégala por un canal seguro; PostgreSQL guarda su hash, no el valor bruto. La API `/api/v1/management` usa `Authorization: Bearer <clave manage>` para emitir y revocar claves, crear destinos y suscripciones, preparar y activar secretos de firma y solicitar replay. Las respuestas de creación de clave y secreto muestran el valor una sola vez; las listas solo incluyen metadatos. La clave `publish` solo publica eventos. El comando interno `uv run --locked python -m eventflow.replay <delivery-uuid>` sigue disponible para operación manual: pide la clave sin mostrarla en los argumentos del proceso.

## Acceso del operador de demo

El operador del servidor crea un usuario de navegador para una organización ya existente con el UUID impreso por `eventflow.bootstrap`:

```bash
uv run --locked python -m eventflow.operator_admin create <organization-uuid> demo-operator
```

El comando imprime una contraseña aleatoria una sola vez; solo su hash `scrypt` queda en PostgreSQL. `rotate demo-operator` genera otra contraseña e invalida sus sesiones; `disable demo-operator` deshabilita el usuario e invalida sus sesiones. Ejecuta esos subcomandos en el servidor, no desde el navegador. La API usa Redis para limitar intentos de login globalmente y por nombre de usuario, y PostgreSQL para comprobar cada sesión y su vencimiento absoluto de ocho horas.

El navegador envía usuario y contraseña a `POST /api/v1/session/login` mediante JSON. Recibe una cookie de sesión opaca `HttpOnly` y una cookie `eventflow_csrf` legible por la aplicación, ambas `SameSite=Strict`; producción marca ambas `Secure`. `GET /api/v1/session` devuelve metadatos de operador y expiración. Las mutaciones bajo `/api/v1/management` y `POST /api/v1/session/logout` con cookie requieren `X-CSRF-Token` igual a `eventflow_csrf`; las lecturas no. La sesión nunca contiene la clave API `manage`. En producción sirve la UI y API desde el mismo origen HTTPS; HTTP sin `Secure` se permite solo con `EVENTFLOW_ENVIRONMENT=development` o `test` en desarrollo aislado.

Para rotar la clave maestra de cifrado, conserva la antigua en `EVENTFLOW_ENCRYPTION_KEYS`, añade una nueva entrada y cambia `EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID` al nuevo identificador en API y worker. Con ambos identificadores aún disponibles, ejecuta:

```bash
uv run --locked python -m eventflow.rotate_master
```

El comando vuelve a cifrar el secreto activo y todas sus versiones conservadas, endpoint por endpoint, y comunica cuántos cambió. Antes de retirar la clave antigua, consulta que ninguna fila de `endpoints.signing_secret_key_id` ni `endpoint_secret_versions.encryption_key_id` la referencia; verifica la operación también en una copia restaurada de PostgreSQL. Retira la clave antigua solo después de esa comprobación. El despachador elimina las versiones de firma retiradas tras su ventana de 24 horas y los agregados de eventos terminales tras 30 días; conserva copias de seguridad según el procedimiento del VPS.

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
