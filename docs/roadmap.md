# Hoja de ruta de implementación

Este archivo define el **plan** y las puertas de los hitos. El avance actual se registra en [project-state.md](project-state.md); la actividad histórica, en [implementation-log.md](implementation-log.md). Evita añadir aquí estados diarios.

El resultado que guía los hitos es **aceptar un evento y entregar un webhook firmado con estado recuperable**, y demostrarlo desde una interfaz usable en un VPS Ubuntu 24.04 LTS. Cada corte grande usa `eventflow-slice` y enlaza requisitos EF con pruebas. Un bug acotado solo necesita causa, cambio y verificación. Los hitos 0–3 consolidan el núcleo backend antes de construir la interfaz; los hitos 4–6 completan operación, UI, rendimiento y despliegue del MVP. La gestión completa de miembros/roles queda fuera del MVP. El aislamiento por organización se mantiene desde el primer corte.

## Hito 0 — Base backend reproducible

Crear backend FastAPI mínimo, configuración por entorno, PostgreSQL/Redis locales, Alembic, pruebas, Ruff, tipos y CI básica. Fijar P-01 y P-02. Documentar en `docs/development.md` únicamente comandos que ya funcionen. Mantener el entorno local compatible con la topología Compose prevista para el VPS; el frontend se construye en el hito 4.

**Puerta:** una copia limpia instala dependencias, inicia la API, aplica una migración a PostgreSQL vacío y supera las comprobaciones backend locales y de CI.

## Hito 1 — Primer recorrido completo

Con una organización y credenciales de desarrollo creadas mediante fixtures, añadir endpoint y suscripción exacta, `POST /api/v1/events` con validación y límite básico de cuerpo, transacción Event/Delivery/outbox, despachador que reintenta publicaciones pendientes, worker con reclamo/lease mínimo, reconciliador de entregas pendientes o vencidas, firma HMAC y receptor local controlable. Registrar estado e intento. Cerrar P-04 antes de iniciar el primer worker y P-03 antes de admitir destinos arbitrarios; la excepción HTTP local existe solo en tests. Acotar timeouts y concurrencia global desde el primer envío. Logs mínimos con IDs permiten seguir el recorrido.

**Puerta:** publicar `order.created` devuelve `202` tras commit; el receptor verifica la firma sobre los bytes recibidos; PostgreSQL muestra una entrega exitosa. Si Redis cae tras el commit, o un aviso publicado se pierde antes de completar el envío, la entrega se recupera desde PostgreSQL sin petición nueva. Una caída de worker con lease vencido también permite retomar el trabajo; las pruebas de concurrencia y resultados tardíos se completan en el hito 2. Toda fila y consulta ya lleva contexto de organización.

## Hito 2 — Fallos, duplicados y concurrencia

Completar idempotencia de ingesta, reintentos con backoff, clasificación de respuestas, carreras de reclamo/lease y resultado tardío, dead letter y replay mediante comando interno con actor de gestión de fixture y auditoría, sin endpoint público de replay todavía. Añadir límites de concurrencia y ritmo por endpoint, más pausa compartida por 429/`Retry-After`; cerrar P-09. Probar caídas entre commit y publicación, muerte del worker, timeout tras recepción, dos workers para una entrega, claves de idempotencia simultáneas y dos destinos con distinta salud.

**Puerta:** EF-02 a EF-08 y EF-13; escenarios 2, 3, 4, 6 y 7 de `spec.md` reproducibles, historia de intentos coherente, límites agregados respetados y ningún trabajo aceptado perdido por fallo recuperable.

## Hito 3 — Límites y autorización backend

Añadir gestión mínima de organizaciones y claves API, incluida una credencial de gestión distinta de la clave de publicación, revocación y autorización de replay y configuración; límite de ingesta por organización, cuotas, calibración de límites de cuerpo y retención. Cerrar P-05/P-06. Mantener pruebas de acceso cruzado y seguridad de salida. La matriz completa de miembros/roles queda para la fase posterior.

**Puerta:** parte backend de EF-01 y EF-08; claves visibles una sola vez, revocación efectiva, replay exclusivo de credencial de gestión, tenant aislado, `429` de ingesta coherente y un receptor lento no agota recursos sin límite. No exponer el servicio a Internet antes de esta puerta ni mientras queden abiertas decisiones de seguridad de despliegue.

## Hito 4 — Operación e interfaz de demostración

Completar API de consulta paginada para eventos, entregas e intentos; métricas, logs correlacionados, salud, pruebas de redacción y documentación operativa. Cerrar P-07 para paginación/filtros, P-10 para sesión de operador y P-11 para receptor de demo. Construir la interfaz React responsive con recorrido guiado de éxito, fallo transitorio, 429 y replay; incluir estados de carga/error, navegación por teclado y permisos. Añadir pruebas de UI y build frontend a CI. Los controles usan operaciones reales y datos de una organización de demostración, sin exponer claves API brutas al navegador.

**Puerta:** EF-09 a EF-11; un revisor completa desde la UI el ciclo feliz y un fallo con reintento/replay, ve estado, intentos, firma verificada y próxima ejecución sin abrir PostgreSQL. La UI pasa revisión funcional en 360, 768 y 1280 px y con teclado; pruebas y build frontend pasan en CI. La API y las métricas permiten corroborar lo mostrado.

## Hito 5 — Rendimiento y ensayo de demo

Benchmark reproducible de ingesta, entrega y receptor fallido; documentar entorno, percentiles, throughput, cuello de botella y cambio medido. Ensayar un recorrido de demostración breve desde un entorno local limpio, con datos reiniciables y sin preparación manual de PostgreSQL. Dimensionar el VPS a partir de esa evidencia y cerrar P-08 antes del despliegue.

**Puerta:** EF-12 y siete escenarios de `spec.md` reproducibles; el README público resume garantías y límites con evidencia y `docs/development.md` permite repetir la demo desde la interfaz.

## Hito 6 — Demo en VPS Ubuntu 24.04 LTS

Desplegar en un único VPS Ubuntu 24.04 LTS con Compose, proxy HTTPS, frontend, API, worker, despachador, PostgreSQL y Redis. Configurar secretos fuera de Git, volumen persistente, health checks, reinicio, backup/restauración y reglas de red/egress verificadas. Documentar despliegue, actualización, rollback y diagnóstico con comandos ejecutados. No abrir la demo a Internet antes de las puertas de seguridad, autenticación, SSRF y límites.

**Puerta:** EF-14 y EF-11: despliegue desde VPS limpio documentado, solo proxy expuesto, UI y API por HTTPS, webhook real procesado, datos persistentes tras reinicio, restauración comprobada y recorrido de reclutador completado en navegador sin secretos ni pasos manuales sobre la BD.

## Fase posterior opcional — Roles completos

Si aporta valor tras completar el MVP, añadir gestión de miembros y matriz owner/admin/developer/viewer, con pruebas por operación. La sesión mínima y la autorización de gestión de la demo ya forman parte del hito 4; esta fase amplía EF-01 sin bloquear la demo.

Cada hito puede dividirse en parches pequeños. Si una prueba revela que un invariante anterior no se cumple, se corrige antes de ampliar el producto.
