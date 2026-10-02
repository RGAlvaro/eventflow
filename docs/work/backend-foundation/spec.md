# Base backend reproducible

Hito 0. Requisitos afectados: EF-11 (parte backend) y base técnica de EF-01/EF-02.

## Comportamiento observable

- Una instalación desde `uv.lock` inicia FastAPI con configuración por entorno.
- `/health/live` responde sin consultar dependencias; `/health/ready` comprueba PostgreSQL y Redis y responde 503 si falta alguna.
- PostgreSQL y Redis se inician localmente con Compose. Alembic aplica la migración inicial a PostgreSQL vacío; la tabla `organizations` usa UUID y conserva la base de aislamiento de los cortes siguientes.
- Las comprobaciones locales y de CI ejecutan pruebas, lint y tipos. Ninguna prueba de BD usa SQLite.

## Fallos y límites

- Configuración de DSN ausente o inválida impide iniciar el proceso, salvo los valores locales explícitos de desarrollo.
- Un fallo de PostgreSQL o Redis hace fallar readiness sin ocultar la dependencia que falló. Liveness sigue operativo.
- Este corte no acepta eventos ni envía webhooks. La puerta completa de EF-11 requiere además frontend y demo en hitos posteriores.
