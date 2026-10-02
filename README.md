# EventFlow

Proyecto de portfolio para demostrar cómo aceptar eventos y entregar webhooks firmados de forma recuperable, observable y segura bajo fallos, duplicados, concurrencia y límites de salida. El resultado final incluye una interfaz responsive y una demo técnica en un VPS Ubuntu 24.04 LTS.

El hito 0 aporta una API FastAPI mínima, configuración por entorno, migración inicial, PostgreSQL/Redis locales y comprobaciones backend. El recorrido de eventos y webhooks comienza en el hito 1 de [la hoja de ruta](docs/roadmap.md).

## Backend local

Requiere Python 3.12, `uv` 0.11.16 y Docker Compose. Las credenciales de `compose.yaml` son solo de desarrollo y los puertos se publican en loopback.

```bash
uv sync --locked
docker compose up -d --wait postgres redis
uv run --locked alembic upgrade head
docker compose up -d --build --wait api
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

La API lee `EVENTFLOW_DATABASE_URL` y `EVENTFLOW_REDIS_URL` (véase `.env.example`). La migración también puede ejecutarse dentro de Compose con `docker compose run --rm api uv run --no-dev --locked alembic upgrade head` si la base aún no está migrada. `/health/live` indica que el proceso atiende peticiones; `/health/ready` comprueba PostgreSQL y Redis.

```bash
EVENTFLOW_TEST_DATABASE_URL=postgresql+asyncpg://eventflow:eventflow@localhost:5432/eventflow uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
```

La prueba de integración se omite cuando falta `EVENTFLOW_TEST_DATABASE_URL`; para verificar el corte completo, arranca Compose, aplica Alembic y define esa variable. CI ejecuta la misma migración y comprobaciones con servicios PostgreSQL y Redis.

## Mapa

| Archivo | Función |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Invariantes y forma de trabajar que Codex carga al abrir el proyecto. |
| [Guía del harness](docs/harness-workflow.md) | Recorrido de una especificación a la entrega, con skills y matrices de verificación. |
| [Especificación](docs/spec.md) | Requisitos y aceptación vigentes. |
| [Arquitectura](docs/architecture.md) | Diseño inicial, garantías y límites técnicos. |
| [Decisiones](docs/decisions.md) | Cambios respecto al dossier y decisiones pendientes. |
| [Hoja de ruta](docs/roadmap.md) | Hitos y puertas de verificación. |
| [Estado del proyecto](docs/project-state.md) | Hito actual, bloqueos y próximo paso en una vista breve. |
| [Registro de implementación](docs/implementation-log.md) | Historial cronológico de trabajo y comprobaciones para lectura humana. |
| [Investigación](docs/research.md) | Fuentes consultadas para el harness y riesgos clave. |
| [Evaluación del harness](docs/harness-evals.md) | Escenarios para comprobar que Codex aplica las instrucciones útiles. |
| `.agents/skills/` | Flujos reutilizables que Codex descubre cuando se inicia aquí. |
| `docs/source/` | Dossier original archivado, sin autoridad sobre los documentos anteriores. |

## Inicio de trabajo

Abre Codex en esta carpeta y pide el hito 1 o un corte funcional de la hoja de ruta. Para trabajo amplio, invoca `$eventflow-slice`. El siguiente objetivo de producto es un recorrido backend completo: aceptar un evento, conservarlo, entregar un webhook firmado y mostrar el resultado mediante API, con un receptor local controlado. Después se añade una interfaz para ejecutar y explicar los escenarios ante un revisor y se despliega en un VPS Ubuntu 24.04 LTS. La gestión completa de roles queda como ampliación opcional. El agente debe producir un cambio verificable y actualizar los criterios correspondientes.

## Garantías previstas

- Un evento aceptado queda en PostgreSQL junto con las entregas y el trabajo recuperable.
- Cada entrega puede realizar varios intentos; el receptor debe tolerar duplicados.
- El estado de las entregas persiste aunque Redis o un worker fallen.
- El envío a destinos arbitrarios requiere protección SSRF en el punto de conexión.

Estas son metas de implementación, no funcionalidades ya terminadas.
