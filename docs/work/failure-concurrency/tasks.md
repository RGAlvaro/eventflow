# Tareas del hito 2

- [x] Idempotencia concurrente por tenant: validación, fingerprint y pruebas de repetición/conflicto.
- [x] Migración para pausa de endpoint y auditoría de replay, aplicada y revisada con PostgreSQL.
- [x] Clasificación, backoff, `Retry-After` y dead letter con reloj controlado y receptor real.
- [x] Capacidad y ritmo compartidos globales/por endpoint; pruebas de dos workers y dos destinos.
- [x] Replay interno autorizado y auditado; historia de generaciones y aislamiento tenant.
- [x] Pruebas de muerte, timeout tras recepción, resultados tardíos y recuperación; revisión de fiabilidad.
- [x] Suite completa sin omisiones, CI verde y cierre mediante PR #5; estado y log actualizados. El merge queda documentado en el historial de la PR.
