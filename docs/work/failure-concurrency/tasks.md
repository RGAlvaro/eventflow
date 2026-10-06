# Tareas del hito 2

- [ ] Idempotencia concurrente por tenant: validación, fingerprint y pruebas de repetición/conflicto.
- [ ] Migración para pausa de endpoint y auditoría de replay, aplicada y revisada con PostgreSQL.
- [ ] Clasificación, backoff, `Retry-After` y dead letter con reloj controlado y receptor real.
- [ ] Capacidad y ritmo compartidos globales/por endpoint; pruebas de dos workers y dos destinos.
- [ ] Replay interno autorizado y auditado; historia de generaciones y aislamiento tenant.
- [ ] Pruebas de muerte, timeout tras recepción, resultados tardíos y recuperación; revisión de fiabilidad.
- [ ] Suite completa sin omisiones, CI verde, PR y merge; estado y log actualizados.
