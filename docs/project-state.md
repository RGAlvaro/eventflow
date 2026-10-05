# Estado actual de EventFlow

Actualizado: 2026-10-05. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 1: primer recorrido backend implementado; corte pendiente de CI y cierre mediante PR. |
| Corte activo | `docs/work/first-webhook-delivery/` en rama `feat/first-webhook-delivery`. |
| Producto existente | Base e ingesta atómica del hito 0/1; despachador, worker Celery, lease, reconciliación, salida HTTPS segura y firma HMAC añadidos en la rama. Todavía no hay frontend ni gestión pública de destinos. |
| Última evidencia | Suite local: 10 pruebas sin omisiones con PostgreSQL y Redis reales, incluida ruta API `202` → Celery → receptor firmado, broker caído, aviso perdido, duplicados, lease vencido y caída real de worker; TLS local con IP fijada y certificado incorrecto. Ruff, mypy, Alembic y arranque Compose pasan. |
| Decisiones inmediatas | P-03 y P-04 cerradas y probadas localmente para hito 1; P-08 detallará y comprobará el bloqueo de salida del VPS antes de exposición pública. |
| Bloqueos externos | Ninguno conocido. |
| Próxima acción | Publicar la PR, comprobar CI verde y fusionar el corte; después iniciar hito 2 (reintentos, idempotencia y límites por endpoint). |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
