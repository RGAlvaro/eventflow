# Plan del hito 2

- Rama: `feat/failure-concurrency` desde `main` actualizado.
- Ingesta: `Idempotency-Key` acotada y fingerprint de JSON canónico; inserción PostgreSQL `ON CONFLICT DO NOTHING` para resolver peticiones concurrentes sin duplicar entregas ni outbox.
- Migración 0003: `endpoints.pause_until`, auditoría tenant de replay e índice de intentos para la ventana de ritmo. El número de intento sigue siendo global por entrega; el presupuesto de siete se cuenta por generación.
- Worker: clasificación de respuesta, backoff exponencial con jitter máximo 15 minutos, `Retry-After` máximo una hora según P-09, capacidad global y por endpoint bajo el mismo bloqueo PostgreSQL. Ninguna espera HTTP mantiene una transacción abierta.
- Replay: servicio y comando interno que autorizan una clave `manage` del tenant, reabren solo `dead_lettered`, aumentan generación, registran actor y crean outbox atómico.
- Pruebas: PostgreSQL y Redis reales para concurrencia, carreras, reintentos, replay y aislamiento; receptor local controlado para respuesta 503→200, 429 y timeout tras recepción. Migración desde base limpia, suite y CI.

Riesgos: una respuesta tardía no debe borrar la pausa ni el resultado de otro intento; los rechazos de capacidad deben conservar trabajo recuperable. Revisar ambos en la revisión de fiabilidad antes de cerrar.
