# Tareas del hito 1

- [x] Crear esquema y migración de dominio con restricciones de tenant; prueba de migración en PostgreSQL.
- [x] Implementar clave de publicación de fixture, ingesta atómica y pruebas de validación/tenant/broker caído.
- [x] Cerrar el diseño P-04: plazos, reclamo con token, reconciliación y parámetros de Celery.
- [ ] Añadir despachador de outbox, worker, lease y reconciliación; probar caída abrupta, aviso perdido, duplicados y vencimiento del lease con PostgreSQL y Redis reales.
- [ ] Cerrar P-03 y añadir salida HTTP segura, firma y receptor local de prueba con escenarios de SSRF.
- [ ] Ejecutar suite completa sin omisiones, escenario de aceptación, CI, revisión de fiabilidad y cierre mediante PR/merge.
