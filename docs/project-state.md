# Estado actual de EventFlow

Actualizado: 2026-10-13. Esta es una **foto breve del presente** para orientar la siguiente tarea; no almacena el historial. La secuencia prevista está en [roadmap.md](roadmap.md) y la actividad pasada en [implementation-log.md](implementation-log.md).

| Aspecto | Estado |
| --- | --- |
| Hito activo | Hito 4 en curso en `feat/hito4-observability-api`; puente de observaciones fusionado en esa rama. |
| Último corte | `docs/work/hito4-operator-demo/` abierto; hito 3 fusionado mediante PR #8. |
| Producto existente | Backend del hito 3; en la rama del hito 4, API paginada, sesión de operador, receptor controlado, puente de observaciones, API de escenarios, métricas tenant y una primera UI React. |
| Última evidencia | PR #10 draft: dos checks verdes del commit `ea288e0`; CI ejecutó 79 pruebas backend sin omisiones, migraciones, Ruff, mypy, prueba y build React. Pruebas Chromium añadidas después, pendientes de CI. |
| Decisiones inmediatas | P-07/P-10/P-11 cerradas. D-17 fija receptor HTTPS externo. P-08 concretará proveedor/dominio, certificado, custodia y egress antes del VPS. |
| Bloqueos externos | Receptor externo HTTPS aún no desplegado; su prueba de DNS/certificado público corresponde al hito 6. |
| Próxima acción | Verificar en CI las pruebas Chromium a 360/768/1280 px y con teclado; completar recorrido E2E con backend y receptor reales. Mantener PR #10 abierta hasta toda la puerta del hito 4. |

Actualiza esta tabla cuando cambie el hito, el corte, una capacidad comprobada, un bloqueo o la siguiente acción. Mantén el detalle de comandos, pruebas y motivos en la entrada correspondiente del log humano, sin copiar aquí su cronología.
