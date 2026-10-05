# Plan del hito 1

- Rama: `feat/first-webhook-delivery`.
- Esquema Alembic y modelos: `api_keys`, `endpoints`, `subscriptions`, `events`, `deliveries`, `delivery_attempts`, `outbox_messages`, todas las filas de dominio con `organization_id`. UUID v4, UTC y JSONB. Restricciones de unicidad para clave de idempotencia por organización, suscripción exacta, evento/endpoint y número de intento.
- API y servicio de ingesta: clave de publicación de fixture guardada solo como hash, límite de cuerpo, validación y transacción única. La API solo devuelve `202` tras commit. Errores estables con `request_id`.
- Despachador y worker Celery: outbox recuperable, aviso duplicable, reclamo con lease PostgreSQL, intento y reconciliación de trabajo pendiente/vencido. P-04 fija lease de 60 s sin renovación, plazo HTTP total de 20 s, límite duro de tarea de 30 s y revisión cada 10 s. Los parámetros Celery y los ensayos de recuperación están en `docs/decisions.md`.
- La capacidad global inicial es de cuatro leases vigentes, protegida con un advisory lock transaccional de PostgreSQL para coordinar varios workers. Fallos básicos se reprograman a 30 s hasta siete intentos; la clasificación y los límites por endpoint se refinan en el hito 2.
- HTTP saliente: P-03 fija HTTPS a dominio público por 443, resolución A/AAAA en cada intento y HTTPX conectado a IP validada con `Host`/SNI original, sin redirecciones ni proxies de entorno; receptor local explícito solo en pruebas. Se probará esta integración antes del primer envío configurable. Firma HMAC sobre bytes exactos y límites de tiempo/concurrencia global.
- Pruebas: migración en PostgreSQL vacío; transacción y tenant; integración con Redis y receptor controlado; broker caído, aviso perdido y lease vencido. CI y `docs/development.md` se actualizan cuando cambien comandos.

Riesgos: la protección SSRF necesita una implementación que preserve SNI/Host al fijar la IP y prueba de DNS rebinding; el lease requiere recuperar trabajo aunque Celery no reentregue. El corte no se cierra hasta demostrar ambos.
