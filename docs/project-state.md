# Estado actual de EventFlow

Actualizado: 2026-10-08. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 4 siguiente: operación e interfaz de demostración. |
| Último corte | Hito 3, `docs/work/hito3-backend-security/`, fusionado mediante PR #8. |
| Producto existente | Backend con ingesta, entrega recuperable, gestión tenant, cifrado y rotación de secretos, cuotas y purga. Aún no hay API de consulta para la UI ni frontend. |
| Última evidencia | PR #8 fusionada como `18b8a21`; ejecuciones 37741957291 y 37741963724 verdes para el último commit: migraciones 0004–0006, `alembic check`, 45 pruebas sin omisiones con PostgreSQL/Redis, Ruff, formato y mypy. |
| Decisiones inmediatas | D-15 fija aprovisionamiento de la primera credencial `manage` mediante comando de operador. P-10/P-11 corresponden al hito 4; P-08 concretará custodia de claves y reglas de salida del VPS. |
| Bloqueos externos | Esta sesión WSL no tiene Docker integrado; integración PostgreSQL/Redis comprobada en CI. Sin bloqueo del hito 3. |
| Próxima acción | Empezar el hito 4: cerrar P-07, P-10 y P-11 antes de construir las superficies que dependen de ellos. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
