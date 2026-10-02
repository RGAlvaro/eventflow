# Estado actual de EventFlow

Actualizado: 2026-10-02. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 1: primer recorrido completo, pendiente de implementación. |
| Corte activo | `docs/work/first-webhook-delivery/` en rama `feat/first-webhook-delivery`; esquema e ingesta son el primer grupo. |
| Producto existente | Base del hito 0 y, en la rama del corte, esquema tenant de eventos/entregas/outbox y `POST /api/v1/events` con clave de publicación de fixture y transacción atómica. Aún no hay despachador, worker ni frontend. |
| Última evidencia | Migración `0002_delivery_foundation` aplicada en PostgreSQL; `alembic check` sin diferencias; 5 pruebas sin omisiones, Ruff y mypy pasan localmente. La ingesta aceptó con broker no disponible y creó una entrega y outbox solo para su tenant. |
| Decisiones inmediatas | P-01, P-02 y diseño P-04 cerrados. Falta comprobar P-04 con el worker real; P-03 sigue pendiente antes de destinos HTTP arbitrarios en hito 1. |
| Bloqueos externos | Ninguno conocido. |
| Próxima acción | Añadir despachador, worker con lease y reconciliación, y probar recuperación y duplicados para validar P-04; después cerrar P-03 antes del primer envío HTTP. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
