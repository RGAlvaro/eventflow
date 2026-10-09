# Estado actual de EventFlow

Actualizado: 2026-10-09. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 4 en curso en `feat/hito4-observability-api`; P-11 se prepara en la rama apilada `feat/hito4-demo-receiver`. |
| Último corte | `docs/work/hito4-operator-demo/` abierto; hito 3 fusionado mediante PR #8. |
| Producto existente | Backend del hito 3; en las ramas del hito 4, API paginada, sesión de operador y receptor controlado independiente con cuatro modos, firma y deduplicación SQLite. Aún no hay integración de observaciones con la API ni frontend. |
| Última evidencia | P-11 local: 61 pruebas sin omisiones con PostgreSQL/Redis y receptor HTTP real; `alembic check`, Ruff, formato y mypy correctos. PR draft #10 conserva la evidencia CI anterior para P-07/P-10. |
| Decisiones inmediatas | P-07/P-10/P-11 cerradas. D-17 fija receptor HTTPS externo. P-08 concretará proveedor/dominio, certificado, custodia y egress antes del VPS. |
| Bloqueos externos | Receptor externo HTTPS aún no desplegado; su prueba de DNS/certificado público corresponde al hito 6. |
| Próxima acción | Publicar y fusionar P-11 en la rama del hito 4 tras CI; después conectar observaciones del receptor con autorización tenant, añadir logs/métricas y construir la UI. Mantener PR #10 abierta hasta toda la puerta del hito 4. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
