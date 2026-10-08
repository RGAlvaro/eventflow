# Estado actual de EventFlow

Actualizado: 2026-10-08. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 4 en curso en `feat/hito4-observability-api`. |
| Último corte | `docs/work/hito4-operator-demo/` abierto; hito 3 fusionado mediante PR #8. |
| Producto existente | Backend del hito 3; en la rama activa, API de consulta paginada de eventos, entregas e intentos con autorización tenant. Aún no hay sesión de navegador ni frontend. |
| Última evidencia | PR draft #10, ejecución 37743935912: migración 0007 y `alembic check` correctos, 46 pruebas sin omisiones con PostgreSQL/Redis, Ruff, formato y mypy. |
| Decisiones inmediatas | P-07 cerrada para paginación por cursor. D-16/D-17 fijan usuario y contraseña para la sesión y receptor HTTPS externo; faltan detalles de P-10/P-11 antes de implementarlos. P-08 concretará custodia de claves y reglas de salida del VPS. |
| Bloqueos externos | Esta sesión WSL no tiene Docker integrado; integración PostgreSQL/Redis comprobada en CI. Sin bloqueo del hito 3. |
| Próxima acción | Concretar P-10 (sesión de operador) y P-11 (receptor HTTPS externo); después implementar ambos y construir la UI. Mantener PR #10 abierta hasta toda la puerta del hito 4. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
