# Estado actual de EventFlow

Actualizado: 2026-10-06. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 2: fallos, duplicados y concurrencia, en implementación. |
| Corte activo | `docs/work/failure-concurrency/` en rama `feat/failure-concurrency`. |
| Producto existente | Base e ingesta atómica del hito 0/1; despachador, worker Celery, lease, reconciliación, salida HTTPS segura y firma HMAC añadidos en la rama. Todavía no hay frontend ni gestión pública de destinos. |
| Última evidencia | Suite local: 10 pruebas sin omisiones con PostgreSQL y Redis reales, incluida ruta API `202` → Celery → receptor firmado, conexión al broker rechazada, aviso perdido, duplicados, lease vencido y caída real de worker; TLS local con IP fijada y certificado incorrecto. Ruff, mypy, Alembic y arranque Compose pasan. CI de la PR #4 pasó instalación, migración, suite, Ruff y mypy. |
| Decisiones inmediatas | P-09 cerrada como diseño para límites compartidos y `Retry-After`; falta probarla con workers reales. P-08 detallará el bloqueo de salida del VPS antes de exposición pública. |
| Bloqueos externos | Docker Desktop no está integrado en esta sesión WSL; las pruebas locales de PostgreSQL/Redis están pendientes. CI puede ejecutar ambos servicios en GitHub. |
| Próxima acción | Implementar primero idempotencia concurrente y migración; después reintentos, capacidad compartida y replay con pruebas reales. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
