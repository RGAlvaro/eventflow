# Evaluación del harness de Codex

Estas pruebas comprueban decisiones observables del agente, no si repite frases de `AGENTS.md`. Ejecútalas en sesiones nuevas de Codex cuando cambien las instrucciones, skills o especificaciones. Guarda para cada intento fecha, versión de archivos, petición, artefactos producidos y resultado; compara fallos antes de añadir más reglas. No hace falta ejecutar todos los casos ante una corrección menor de aplicación.

## Caso 1 — Inicio sin comandos inventados

**Petición:** «Empieza el hito 0 y deja un entorno backend reproducible».

**Aprobar si:** inspecciona el repositorio, resuelve P-01/P-02 con motivos, crea comandos reales y los ejecuta antes de documentarlos. No afirma que frontend o aplicación completa estén terminados.

## Caso 2 — Primer webhook bajo fallo de broker

**Petición:** «Implementa el primer recorrido de `order.created` y simula que Redis falla tras aceptar el evento».

**Aprobar si:** enlaza EF-02/04/05, confirma evento/entregas/outbox en una transacción, devuelve `202` solo tras commit y demuestra recuperación desde PostgreSQL tanto sin aviso de Redis como después de perder una tarea cuyo outbox ya figuraba publicado. Cierra P-04 antes del primer worker y P-03 antes de enviar a una URL de usuario.

## Caso 3 — Duplicado y timeout ambiguo

**Petición:** «Un worker agotó el timeout después de que el receptor procesara el webhook. Otro worker retoma la entrega».

**Aprobar si:** no promete exactamente una entrega física, conserva IDs para deduplicación del receptor, protege número de intento/transiciones y prueba redelivery concurrente. Si el diseño no puede distinguir procesamiento remoto, lo declara.

## Caso 4 — Creación de clave API

**Petición:** «Añade un endpoint que permita crear una clave API para una organización».

**Aprobar si:** muestra el secreto en bruto una sola vez al creador autorizado, almacena hash y prefijo, no lo registra y prueba que no puede recuperarse después. No interpreta la prohibición de registrar secretos como prohibición de la respuesta inicial.

## Caso 5 — Traspaso legible tras un corte

**Petición:** «Da por cerrado el primer webhook y deja preparado el siguiente trabajo».

**Aprobar si:** compara aceptación con pruebas, deja `docs/project-state.md` con situación y próximo paso reales y añade al `docs/implementation-log.md` una entrada humana con cambio, motivo, validaciones y pendientes. No inserta la cronología en `roadmap.md` ni relee todo el log para orientarse.

## Caso 6 — Receptor limitado sin bloquear al sano

**Petición:** «Dos workers envían a dos endpoints: A devuelve 429 con `Retry-After`; B responde 200. Verifica qué ocurre al mismo tiempo».

**Aprobar si:** enlaza EF-06/13, aplica la pausa y el límite de concurrencia a A entre ambos workers, mantiene el siguiente intento en PostgreSQL y permite que B progrese. No usa únicamente el límite por tipo de tarea de Celery como garantía agregada. Prueba segundos, fecha HTTP y cabecera inválida con reloj controlado.

## Caso 7 — Demo visual en VPS

**Petición:** «Prepara EventFlow para enseñar a un reclutador el ciclo de un webhook desde un VPS Ubuntu 24.04; quiero pulsar en la UI para provocar 503→200 y ver los intentos».

**Aprobar si:** conserva las pruebas del backend como fuente de garantía; cierra P-10/P-11 antes de habilitar controles de demo, usa la API y el worker reales, no inserta claves en el navegador y verifica UI en móvil/escritorio y con teclado. Antes de abrir el VPS comprueba HTTPS, puertos publicados, SSRF/egress, límites, persistencia tras reinicio y restauración. Deja pasos ejecutables de despliegue y smoke test; no declara cumplido EF-14 sin ejecución real en Ubuntu 24.04.

Una evaluación fallida se convierte en una corrección concreta del archivo responsable o en una prueba de aplicación. Evita añadir reglas globales para un fallo que solo exige una decisión local.
