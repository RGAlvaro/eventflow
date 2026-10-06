# Estado actual de EventFlow

Actualizado: 2026-10-06. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 2 verificado; el siguiente trabajo corresponde al hito 3. |
| Último corte | `docs/work/failure-concurrency/`, entregado mediante PR #5. |
| Producto existente | Ingesta idempotente por organización, reintentos y dead letter, replay interno auditado, límites compartidos globales y por endpoint, pausa por 429 y recuperación desde PostgreSQL. Todavía no hay frontend ni gestión pública de claves y destinos. |
| Última evidencia | CI de la PR #5, ejecución 37431155952: migración 0003 y `alembic check` correctos; 32 pruebas pasadas sin omisiones con PostgreSQL y Redis reales, incluidos dos workers Celery, receptor real, conflictos de idempotencia y replay; Ruff, formato y mypy correctos. |
| Decisiones inmediatas | P-09 implementada y probada. P-05/P-06 preceden a la gestión de claves y límites de ingesta del hito 3; P-08 detallará el bloqueo de salida del VPS antes de exposición pública. |
| Bloqueos externos | Esta sesión WSL no tiene Docker integrado; la integración completa se ejecutó en CI. No hay bloqueo del producto por ello. |
| Próxima acción | Iniciar hito 3: cerrar P-05/P-06 y preparar gestión de claves, autorización y límites de ingesta en rama propia. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
