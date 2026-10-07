# Especificación de producto v0.1

Estado: base de implementación revisable. Fuente de origen: `source/eventflow_project_dossier.md`. Este documento prevalece cuando contradice al dossier.

## Propósito y alcance

EventFlow permite a una organización registrar destinos HTTP, suscribirse a tipos de evento exactos, publicar eventos con una clave API y observar el ciclo de entrega de webhooks firmados. Su objetivo principal es demostrar entrega asíncrona fiable bajo fallos, reintentos, duplicados, concurrencia y límites de ingesta y salida. El **MVP de portafolio** incluye un núcleo backend verificable, una interfaz gráfica responsive para ejecutar y explicar escenarios reales y una demo funcional en un único VPS Ubuntu 24.04 LTS. El backend se termina y prueba primero; la interfaz no sustituye sus pruebas de fiabilidad. La gestión completa de miembros/roles queda fuera del MVP.

Quedan fuera del MVP: gestión completa de miembros/roles, ejecución de código del usuario, flujos visuales, Kafka, Kubernetes, facturación, GraphQL, entrega exactamente una vez, orden global y despliegue multirregión. La demo en VPS es parte del MVP; su exposición por Internet exige superar las puertas de seguridad y operación antes de abrir el acceso.

## Requisitos y aceptación

| ID | Requisito | Evidencia mínima |
| --- | --- | --- |
| EF-01 | Antes de exposición pública, una organización administra claves API, endpoints y suscripciones con autorización explícita; la gestión completa de miembros y roles owner/admin/developer/viewer pertenece a la fase posterior. | En el MVP backend, pruebas de acceso cruzado, credenciales revocadas y replay reservado a una credencial de gestión; en la fase posterior, matriz de permisos por rol. |
| EF-02 | `POST /api/v1/events`, autenticado por clave API, valida tipo y tamaño, persiste evento y entregas de suscripciones exactas y responde `202` solo tras confirmar trabajo recuperable. | Prueba de ingesta, varias suscripciones y fallo del broker tras commit. |
| EF-03 | `Idempotency-Key` es opcional y se limita por organización. Repetir clave y petición devuelve el evento original; reutilizarla con contenido distinto devuelve `409`. | Pruebas concurrentes de repetición y conflicto sin filas duplicadas. |
| EF-04 | Cada destino recibe cuerpo JSON determinista con IDs estables, generación de replay, timestamp por intento, identificador de versión del secreto y firma HMAC-SHA256 `v1`; se documenta la verificación, rotación y deduplicación del consumidor. | Receptor de prueba comprueba firma sobre bytes enviados, distingue la versión del secreto durante una rotación, deduplica reintentos dentro de una generación y admite un replay explícito. |
| EF-05 | Cada par evento/endpoint genera una entrega lógica. Los intentos son trazables, y transiciones y números de intento siguen siendo coherentes ante workers concurrentes o tareas repetidas. | Pruebas de concurrencia, caída de worker y redelivery. |
| EF-06 | Se reintentan errores de red, timeout, 408, 429 y 5xx con backoff exponencial y jitter acotado; un `Retry-After` válido en 429 retrasa también la siguiente entrega al mismo endpoint. 2xx finaliza con éxito; 3xx no se sigue; el resto de 4xx termina salvo decisión documentada. | Pruebas de clasificación, `Retry-After` en segundos/fecha HTTP y calendario con reloj controlado. |
| EF-07 | Tras agotar intentos, la entrega pasa a `dead_lettered`. Replay explícito agrega intentos sin borrar historial y deja rastro de quién lo solicitó. | Receptor fallido → dead letter → recuperación → replay exitoso. |
| EF-08 | El sistema rechaza destinos internos/no permitidos y evita que DNS, redirecciones o configuración de proxy salten el control. | Casos IPv4/IPv6, localhost, rangos privados, cambio DNS y redirección. |
| EF-09 | La interfaz permite al operador autenticado preparar escenarios controlados, publicar un evento de prueba, observar estado e intentos, inspeccionar el calendario de reintentos y activar replay cuando esté autorizado. Es usable con teclado, muestra estados de carga/error/vacío y se adapta a móvil y escritorio. | Recorrido E2E real, sin respuestas simuladas del backend, para éxito, 503→200, dead letter/replay y 429; revisión en anchos de 360, 768 y 1280 px sin desbordamiento horizontal ni controles inaccesibles. |
| EF-10 | Logs y métricas permiten seguir un evento de la ingesta al intento. No exponen secretos ni cuerpos de respuesta del receptor. | Pruebas de redacción y observación de IDs, estados y latencias. |
| EF-11 | El entorno local y CI ejecutan migraciones, pruebas, lint y tipos de backend, más pruebas y build de frontend, de forma reproducible. | Instalación limpia y CI verdes; la demo desplegada supera un smoke test de interfaz, API, worker y entrega real. |
| EF-12 | Hay benchmark reproducible de ingesta, entrega y receptor fallido, con entorno y percentiles publicados; no se afirman cifras sin medir. | Script y `docs/performance.md` con resultados reales. |
| EF-13 | La salida HTTP limita concurrencia y ritmo por endpoint entre todos los workers, además de la concurrencia global; un destino lento o que devuelve 429 no bloquea a los demás. | Prueba con varios workers y dos destinos: uno lento o con 429, otro sano; no se exceden límites y el segundo progresa. |
| EF-14 | La aplicación y su demo técnica funcionan en un único VPS Ubuntu 24.04 LTS con HTTPS, datos persistentes, servicios reiniciables y un procedimiento reproducible de despliegue, copia/restauración y diagnóstico. Solo el proxy publica puertos; PostgreSQL, Redis y los servicios internos quedan privados. | Desde un VPS limpio se despliega la versión documentada; tras reiniciar servicios/host siguen accesibles datos y UI; se prueba restauración y el recorrido de un webhook real desde el navegador. |

El primer corte funcional puede usar una organización y credenciales de desarrollo creadas por fixtures, sin interfaz de usuario. Debe demostrar ingesta, persistencia, aviso recuperable, envío firmado y estado observado antes de construir la interfaz. Esta secuencia no relaja el aislamiento: toda fila y consulta afectada sigue ligada a su organización desde el principio. La demo final dispone de una credencial de gestión diferenciada de la clave de publicación; replay y configuración de destinos nunca se autorizan con una clave de publicación.

## Contratos iniciales

- API versionada con prefijo `/api/v1`, errores estables con `code`, `message` y `request_id`; listados paginados.
- Tipos de evento en minúsculas con separadores `.`/`_`/`-`; suscripciones de coincidencia exacta. Límite inicial de cuerpo: 256 KiB, configurable.
- IDs UUID v4. Tiempos UTC con zona horaria. Payload JSON almacenado en PostgreSQL JSONB.
- La clave API en bruto se muestra una sola vez al creador autorizado y nunca se registra ni se persiste en claro; después se usa su hash para verificarla.
- No se garantiza orden entre eventos ni entre endpoints. Para no procesar dos veces un reintento y permitir un replay explícito, el consumidor usa `(delivery_id, generation)` como clave de deduplicación del efecto; puede usar `event_id` si su negocio nunca debe reprocesar ese evento.
- Las respuestas HTTP de endpoints no se siguen por redirección. La petición saliente tiene límites explícitos de tiempo y tamaño.
- El límite de ingesta por organización se implementa antes de exposición pública; P-06 fija valores iniciales y una prueba de carga los calibra antes de abrir el servicio.
- La presión sobre destinos externos se limita por endpoint desde el hito 2. `Retry-After` acepta segundos o fecha HTTP; un valor inválido usa backoff ordinario y uno válido se acota por una política documentada antes de implementar el hito 2. La pausa de un endpoint no bloquea a los demás.

## Escenarios de demostración

1. Desde la interfaz, un operador publica `order.created`; el receptor devuelve 200 y la pantalla muestra éxito, intento, firma comprobada y latencia obtenidos de la API real.
2. El receptor devuelve 503 dos veces y luego 200; se ven tres intentos y el calendario de reintento.
3. Un receptor que falla llega a `dead_lettered`; tras recuperarse, el replay preserva intentos anteriores y termina con éxito.
4. Dos peticiones simultáneas con la misma clave de idempotencia producen un único evento y un único conjunto de entregas.
5. Una URL interna y un acceso a otra organización se rechazan; los logs permanecen libres de secretos.
6. Una interrupción entre commit y publicación al broker no pierde la entrega: el despachador o reconciliador la recupera.
7. Un destino devuelve 429 con `Retry-After` mientras otro responde 200; se respeta la pausa del primero sin detener el segundo ni superar su límite de concurrencia.

Cada implementación debe enlazar los IDs EF afectados con pruebas o evidencia observable. Los detalles aún no definidos se cierran en `decisions.md` antes del corte que los necesita.

En la demo del VPS, los escenarios de fallo usan un receptor controlado y destinos preconfigurados. La UI pública no permite introducir URLs internas ni desactivar SSRF, y el acceso de operador está protegido; los controles de demo no pueden alterar datos de otras organizaciones. El flujo debe poder repetirse ante un revisor sin preparar la base a mano ni revelar secretos.
