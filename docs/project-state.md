# Estado actual de EventFlow

Actualizado: 2026-10-08. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 4 en curso en `feat/hito4-observability-api`. |
| Último corte | `docs/work/hito4-operator-demo/` abierto; hito 3 fusionado mediante PR #8. |
| Producto existente | Backend del hito 3; en la rama activa, API de consulta paginada y sesión de operador con contraseña, cookies, CSRF, revocación y auditoría tenant. Aún no hay receptor de demo ni frontend. |
| Última evidencia | PR draft #10, ejecución 37747354959: migraciones 0007–0008 y `alembic check` correctos, 49 pruebas sin omisiones con PostgreSQL/Redis, Ruff, formato y mypy. |
| Decisiones inmediatas | P-07/P-10 cerradas. D-17 fija receptor HTTPS externo; P-11 requiere su contrato operativo antes de implementarlo. P-08 concretará custodia de claves y reglas de salida del VPS. |
| Bloqueos externos | Esta sesión WSL no tiene Docker integrado; integración PostgreSQL/Redis comprobada en CI. Sin bloqueo del hito 3. |
| Próxima acción | Cerrar P-11 e implementar el receptor HTTPS externo controlado; después observabilidad y UI. Mantener PR #10 abierta hasta toda la puerta del hito 4. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
