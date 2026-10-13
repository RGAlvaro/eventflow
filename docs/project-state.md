# Estado actual de EventFlow

Actualizado: 2026-10-13. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 4 cerrado; hito 5, rendimiento y ensayo de demo, por iniciar. |
| Último corte | `docs/work/hito4-operator-demo/` cerrado mediante PR #10, fusionada en `main` (`693f4f5`). |
| Producto existente | Backend fiable y autorizado, receptor controlado, observaciones, métricas, API de escenarios y UI React responsive con login, intentos, pausa y replay. |
| Última evidencia | PR #10 fusionada tras dos checks verdes: migraciones, 79 pruebas backend sin omisiones, Ruff, formato, mypy, prueba/build React y cuatro pruebas Chromium. Capturas revisadas a 360/768/1280 px; E2E con API, PostgreSQL/Redis, receptor firmado y replay. |
| Decisiones inmediatas | P-07/P-10/P-11 cerradas. D-17 fija receptor HTTPS externo. P-08 concretará proveedor/dominio, certificado, custodia y egress antes del VPS. |
| Bloqueos externos | Receptor externo HTTPS aún no desplegado; su prueba de DNS/certificado público corresponde al hito 6. |
| Próxima acción | Iniciar hito 5: benchmark reproducible de ingesta, entrega y receptor fallido; ensayar la demo desde un entorno limpio y medir para cerrar P-08 antes del VPS. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
