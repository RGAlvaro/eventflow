# Plan breve

1. Incorporar una clave maestra por entorno y una utilidad de cifrado autenticado con metadatos de versión. Migrar secretos existentes sin aceptar texto plano en runtime. Añadir versión al webhook y probar manipulación, ausencia de clave y recuperación del worker.
2. Añadir API de gestión con autenticación `manage`, altas/revocación de claves, destinos y suscripciones, rotación del secreto y replay autorizado. Aplicar límites de recursos en transacciones PostgreSQL y auditoría.
3. Añadir bucket atómico Redis, cuota diaria y contador de entregas pendientes en PostgreSQL. Mantener el commit de evento, entregas y outbox atómico; probar admisión concurrente y caída de Redis.
4. Añadir reloj de retención y purga por agregado bajo bloqueo. Probar carreras con replay y trabajo pendiente.
5. Revisar fiabilidad/tenant/SSRF, ejecutar suite y migraciones completas en CI, documentar operación y cerrar PR solo al cumplir la aceptación.

Riesgos principales: la migración no puede descifrar un secreto histórico perdido; debe exigir la clave maestra al migrar filas existentes. La ausencia de clave durante el envío no puede consumir el presupuesto de intentos. Los límites Redis pueden rechazar antes del commit, pero Redis no almacena trabajo aceptado. P-08 fijará custodia y restauración de claves del VPS.
