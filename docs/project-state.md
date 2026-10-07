# Estado actual de EventFlow

Actualizado: 2026-10-07. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 2 verificado; preparación de seguridad del hito 3 en la rama `docs/close-p05-p06`. |
| Último corte | `docs/work/failure-concurrency/`, entregado mediante PR #5; P-05/P-06 cerradas como diseño en la rama actual, pendientes de integración. |
| Producto existente | Ingesta idempotente por organización, reintentos y dead letter, replay interno auditado, límites compartidos globales y por endpoint, pausa por 429 y recuperación desde PostgreSQL. Todavía no hay frontend ni gestión pública de claves y destinos. |
| Última evidencia | CI de la PR #5, ejecución 37431155952: migración 0003 y `alembic check` correctos; 32 pruebas pasadas sin omisiones con PostgreSQL y Redis reales, incluidos dos workers Celery, receptor real, conflictos de idempotencia y replay; Ruff, formato y mypy correctos. |
| Decisiones inmediatas | P-05/P-06 tienen contrato de diseño; cifrado, rotación, autorización, límites y retención siguen sin implementar ni probar. P-08 detallará el bloqueo de salida y custodia de claves del VPS antes de exposición pública. |
| Bloqueos externos | Esta sesión WSL no tiene Docker integrado; la integración completa se ejecutó en CI. No hay bloqueo del producto por ello. |
| Próxima acción | Verificar y entregar esta rama documental; después abrir un corte funcional del hito 3 para implementar P-05/P-06, empezando por cifrado de secretos y gestión autorizada de claves y endpoints. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
