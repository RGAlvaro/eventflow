# Arquitectura e invariantes

Estado: diseño inicial. Los componentes concretos se implementarán por cortes de `roadmap.md`; este documento expresa el contrato que deben satisfacer.

## Componentes

```text
Navegador → proxy HTTPS → React SPA y FastAPI → PostgreSQL (eventos, entregas, intentos, outbox)
                                         ↘ Redis (broker, límite de ingesta)
PostgreSQL → despachador/reconciliador → Celery/Redis → workers → destinos HTTP
```

Monorepo con API y workers separados, una base PostgreSQL compartida y Redis como broker/estado efímero. FastAPI, Python 3.12+, Pydantic v2, SQLAlchemy 2 async para la API, Alembic, Celery y httpx son la base propuesta; React/TypeScript/Vite cubre la interfaz. Los workers pueden usar acceso síncrono a PostgreSQL si simplifica Celery; no se comparten sesiones entre tareas. No hay microservicios de dominio en el MVP. El destino de ejecución es un único VPS Ubuntu 24.04 LTS, con imágenes/servicios ejecutables mediante Docker Compose; el desarrollo local debe reproducir esa topología sin fijar aún proveedor de VPS.

## Camino de ingestión

1. Autenticar clave API y organización; validar tipo, JSON, tamaño y límite de ingesta.
2. En **una transacción PostgreSQL**, reservar idempotencia, insertar `Event`, crear una `Delivery` por endpoint activo y suscrito e insertar mensajes de outbox para las entregas. Una repetición idéntica recupera el resultado original; una petición distinta con la misma clave da `409`.
3. Confirmar la transacción y devolver `202` con el ID del evento. No depender de que Redis esté disponible para decidir si el evento quedó aceptado.
4. Un despachador publica mensajes de outbox al broker y marca progreso. Publicar y marcar no es atómico: los avisos duplicados se toleran. Desde el primer worker, un reconciliador consulta PostgreSQL y reactiva entregas pendientes sin aviso y entregas cuyo lease venció, incluso si el outbox figura como publicado. La recuperación no depende exclusivamente de redelivery de Celery.

Restricciones de base: unicidad de `(organization_id, idempotency_key)` cuando la clave exista y de `(event_id, endpoint_id)`; fingerprint de tipo/payload para detectar conflicto. La clave de idempotencia debe tener formato y longitud acotados. Outbox y entrega son durables; Celery es un mecanismo de activación, no la fuente de verdad.

## Camino de entrega

Una tarea recibe solo `delivery_id`. Reclama la entrega con una transición condicional protegida en PostgreSQL, registra el intento y un lease/token; cierra la transacción **antes** de realizar HTTP. Al terminar, actualiza la entrega solo si sigue poseyendo el lease. Si un intento termina después de perder el lease, registra su resultado como tardío, pero no cambia el estado ni la planificación de la entrega actual. Un lease vencido permite recuperación, por lo que dos envíos físicos pueden coexistir; los IDs estables y la firma hacen visible esa posibilidad. `DeliveryAttempt` conserva el resultado de cada envío observado y tiene número único por entrega. El estado y el número se asignan transaccionalmente. El hito 1 implementa la versión mínima de reclamo y reconciliación; el hito 2 prueba y amplía las carreras y los reintentos.

Estados base: `pending → processing → succeeded | retry_scheduled | dead_lettered`; `retry_scheduled → processing`; `dead_lettered → pending` solo con replay autorizado. Puede añadirse `cancelled` para endpoint desactivado cuando se precise la semántica. Replay inicia una nueva generación de intentos con presupuesto de reintentos propio y conserva la historia anterior. El máximo inicial es siete intentos por generación, configurable. No se mantiene una transacción de BD abierta durante el request HTTP.

Reintentos debidos se consultan en PostgreSQL mediante `next_attempt_at`; no se delega su única copia a un temporizador de Redis/Celery. Backoff exponencial con jitter, máximo 15 minutos y clasificación de `spec.md`. Un timeout del emisor no prueba que el receptor no procesó la petición. El resultado del producto es *at least once*, sin promesa de exactamente una vez ni de orden.

Antes de reclamar, se comprueba de forma atómica una capacidad global y otra por endpoint, compartidas por todos los workers; las tareas que no obtienen capacidad permanecen programadas en PostgreSQL. La pausa por 429/`Retry-After` se guarda por endpoint, de modo que un destino limitado no frene a otro. No se confía en `rate_limit` de Celery como límite agregado entre workers. Los valores, el algoritmo de ritmo y el máximo de espera se fijan con P-09 antes del hito 2; la concurrencia básica y los timeouts acotados comienzan en el hito 1.

## Contrato de firma del webhook

Cada POST lleva `X-EventFlow-Event-Id`, `X-EventFlow-Delivery-Id`, `X-EventFlow-Generation`, `X-EventFlow-Timestamp` (segundos Unix UTC) y `X-EventFlow-Signature: v1=<hex HMAC-SHA256>`. La entrada de HMAC es el UTF-8 de `timestamp + "."` seguido de los **bytes exactos del cuerpo HTTP enviado**. Se serializa el cuerpo una sola vez por intento; el receptor verifica contra esos bytes antes de parsear JSON. Los IDs de evento y entrega y la generación permanecen estables en reintentos; un replay incrementa la generación. El timestamp y la firma se regeneran en cada intento, para que la verificación temporal del receptor no rechace un reintento legítimo tardío. El cuerpo firmado incluye ambos IDs, generación y un tipo/versión de evento; su esquema exacto se fija con una prueba de contrato en el primer corte. El receptor comprueba que los IDs y la generación de las cabeceras coinciden con los del cuerpo firmado. La clave de firma pertenece al endpoint y su identificación/rotación se cierran antes de exposición pública. Un receptor de ejemplo verifica firma, tolerancia temporal configurable y deduplicación por `(delivery_id, generation)`, por lo que el replay solicitado puede volver a procesarse.

## Seguridad

- **Tenancy:** cada acceso humano o de worker resuelve organización desde una credencial o relación verificada. Los IDs recibidos del cliente nunca sustituyen ese contexto. Pruebas de acceso cruzado son obligatorias.
- **Claves:** claves API generadas con CSPRNG, mostradas una vez, almacenadas con hash y prefijo identificador; revocables. Secretos de firma cifrados porque deben recuperarse para firmar. Material de cifrado fuera del repositorio; definir rotación y manejo de pérdida de clave antes de despliegue público.
- **Autorización backend e interfaz:** en los cortes iniciales, fixtures locales separan clave de publicación y credencial de gestión. Replay, destinos y consultas se autorizan con contexto de organización y alcance de gestión; nunca con una clave de publicación. Antes de exposición pública se define provisión, revocación y auditoría de ambas credenciales. La interfaz usa una sesión de operador autenticado definida en P-10; ninguna clave API bruta ni secreto de firma se incrusta en el bundle o almacenamiento del navegador. Los controles de demo llaman a operaciones autorizadas del backend y usan datos de una organización de demostración aislada.
- **SSRF:** P-03 admite en producción solo HTTPS a nombres DNS públicos por el puerto 443. HTTP local solo se habilita explícitamente en pruebas o desarrollo aislado. En cada intento se valida la URL, se resuelven A y AAAA, se rechaza el host si alguna dirección no es pública y se conecta a una IP validada conservando `Host`, SNI y verificación TLS del nombre original. No se siguen redirecciones ni se usan proxies de entorno; el VPS bloquea salida no autorizada a redes internas sin cortar el acceso necesario a PostgreSQL, Redis y DNS. Validar únicamente al registrar o resolver antes de conectar sin fijar la IP deja una ventana de DNS rebinding.
- **Salida HTTP:** timeouts de conexión/lectura/escritura/pool, respuesta acotada y User-Agent definido. No persistir cuerpo de respuesta por defecto; guardar estado, latencia y error categorizado/sanitizado. Evitar secretos en logs y trazas.

La protección SSRF se desarrolla y prueba **antes del primer envío a una URL aportada por usuario**. Un receptor local de pruebas usa configuración explícita del entorno de test; esa excepción no entra en producción.

## Observabilidad y prueba

Logs JSON con `request_id`, `organization_id`, `event_id`, `delivery_id`, `attempt_id` cuando proceda. Métricas: ingesta aceptada/rechazada, entregas por estado, intentos/reintentos, latencias, backlog de outbox, entregas vencidas y edad del trabajo pendiente. `/health/live` no consulta dependencias; `/health/ready` comprueba las necesarias con límites de tiempo.

Pruebas unitarias para firmas, transiciones, políticas de retry y validaciones; integración real con PostgreSQL y Redis para transacciones, concurrencia, tenant e idempotencia; E2E con receptor controlable. SQLite no sustituye pruebas de concurrencia PostgreSQL. Una prueba de interrupción entre commit y publicación comprueba recuperación. CI debe ejecutar migraciones en una BD limpia.

## Interfaz de demostración

La interfaz muestra una ruta guiada corta: elegir un escenario seguro (200, 503→200, 429 o fallo hasta dead letter), publicar un evento de ejemplo, seguir estado e intentos y reintentar mediante replay autorizado. El receptor controlado publica a la API solo resultados sanitizados, incluida la verificación de firma; la pantalla no finge resultados ni lee PostgreSQL directamente. La navegación y los controles funcionan con teclado y en anchos de móvil y escritorio; se muestran carga, errores, permisos insuficientes y estados vacíos. El panel de diagnóstico enlaza IDs de evento, entrega e intento y presenta la próxima ejecución/pausa por rate limit.

## Despliegue en VPS

En Ubuntu 24.04 LTS, usar Docker Engine y Compose para proxy HTTPS, frontend estático, API, worker, despachador/reconciliador, PostgreSQL y Redis. Mantener imágenes y configuración de producción versionadas; no montar código fuente mutable en contenedores de producción. Publicar solo 80/443 en el proxy, con PostgreSQL, Redis y API en redes privadas; comprobar los puertos realmente expuestos y las reglas de salida del worker, sin suponer que UFW limita los puertos publicados por Docker. Persistir PostgreSQL en volumen y documentar copia, restauración comprobada, migraciones, reinicio, rollback y diagnóstico con logs/health checks. Los secretos de producción se suministran fuera de Git mediante mecanismo acotado a cada servicio. La demo no se hace pública antes de completar SSRF, autenticación, límites de ingesta/salida y la puerta de seguridad del hito 3.

El receptor de demo será controlado y con destinos preconfigurados; su conectividad y aislamiento se fijan en P-11 antes de construir la demo del VPS. Esa ruta no introduce una excepción general que permita conectar a redes internas ni autoriza a usuarios públicos a cambiar el destino. El dominio, certificado TLS, proveedor, tamaño del VPS y política exacta de backup/egress se cierran en P-08 antes del despliegue.
