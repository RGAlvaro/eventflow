# Estado actual de EventFlow

Actualizado: 2026-10-02. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 0: base backend implementada y verificada localmente; falta confirmar el primer job de CI. |
| Corte activo | `docs/work/backend-foundation/`; implementación local hecha, validación CI pendiente. |
| Producto existente | API FastAPI mínima con health checks, configuración, migración inicial de organizaciones, Compose, lockfile y CI backend. Aún no hay ingesta, worker ni frontend. |
| Última evidencia | Instalación con `uv sync --locked`; migración sobre PostgreSQL vacío; 3 pruebas, Ruff y mypy pasan. Imagen API construida y `/health/ready` respondió con PostgreSQL y Redis disponibles. |
| Decisiones inmediatas | P-01 y P-02 cerradas. P-04 antes del primer worker y P-03 antes de destinos HTTP arbitrarios en hito 1. |
| Bloqueos externos | La ejecución del workflow de GitHub requiere publicar el repositorio; no se ha observado aún un job de CI. |
| Próxima acción | Confirmar CI backend en GitHub y comenzar el hito 1 con `eventflow-slice`, cerrando P-03/P-04 antes de salida HTTP y worker. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
