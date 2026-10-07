# Estado actual de EventFlow

Actualizado: 2026-10-07. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 3 implementado y verificado en la PR #8; hito 4 siguiente. |
| Último corte | `docs/work/hito3-backend-security/`: P-05/P-06, gestión, límites y retención implementados. |
| Producto existente | Backend con ingesta, entrega recuperable, gestión tenant, cifrado y rotación de secretos, cuotas y purga. Aún no hay API de consulta para la UI ni frontend. |
| Última evidencia | PR #8, ejecución 37639852892: migraciones 0004–0006 y `alembic check` correctos; 45 pruebas, ninguna omitida, con PostgreSQL y Redis reales; Ruff, formato y mypy correctos. |
| Decisiones inmediatas | D-15 fija aprovisionamiento de la primera credencial `manage` mediante comando de operador. P-10/P-11 corresponden al hito 4; P-08 concretará custodia de claves y reglas de salida del VPS. |
| Bloqueos externos | Esta sesión WSL no tiene Docker integrado; integración PostgreSQL/Redis comprobada en CI. Ningún bloqueo funcional del hito 3. |
| Próxima acción | Comenzar hito 4 con P-07, P-10 y P-11; después calibrar límites en hito 5. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
