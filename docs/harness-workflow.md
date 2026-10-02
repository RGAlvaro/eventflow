# Cómo funciona el harness de EventFlow

Esta guía describe **el flujo de trabajo previsto**, desde pedir una funcionalidad hasta declarar cerrado un corte. El proyecto todavía contiene especificación e instrucciones, no una aplicación ejecutable. Por eso distingue entre comprobaciones disponibles hoy y pruebas que se incorporarán durante los hitos.

**Corte** significa una porción acotada de trabajo que produce un resultado observable de extremo a extremo. Puede cubrir una parte de un hito, varios requisitos EF y varias tareas de código, pruebas y documentación. Por ejemplo, «aceptar `order.created`, guardarlo y entregar un webhook firmado al receptor de prueba» es un corte; «crear el modelo Event» es solo una tarea dentro de él.

## La idea en un minuto

El harness mantiene una cadena de trazabilidad:

```text
Petición → requisito EF → especificación del corte → plan → tareas
        → código y pruebas → revisión → comparación con aceptación → entrega
```

La regla de producto que atraviesa esa cadena es que un evento aceptado debe permanecer recuperable y poder convertirse en una entrega webhook firmada, incluso si Redis o un worker fallan. `AGENTS.md` recuerda las invariantes en cada sesión; los documentos y skills añaden detalle solo cuando la tarea lo requiere.

## Hito, corte y tarea: tres escalas distintas

| Escala | Qué representa | Ejemplo | Cuándo se cierra |
| --- | --- | --- | --- |
| **Hito** | Una etapa del producto con una puerta de salida en `docs/roadmap.md`. | Hito 1: primer recorrido de entrega. | Cuando la evidencia exigida por su puerta está disponible. Puede requerir varios cortes. |
| **Corte** | Una entrega acotada y observable de extremo a extremo, especificada en `docs/work/<slug>/`. | Aceptar `order.created`, persistirlo y entregar un webhook firmado al receptor de prueba. | Cuando pasan sus criterios de aceptación y la revisión de riesgos aplicable. No basta con completar la lista de tareas. |
| **Tarea** | Una unidad de implementación o comprobación dentro del corte. | Crear la migración de `Delivery` y probarla. | Cuando se ha realizado y verificado según `tasks.md`. |

Un corte puede cubrir varios requisitos EF y parte de un hito. Si un corte revela trabajo adicional, se registra en sus tareas o se abre otro corte; no se declara terminado por tener código escrito. Para un bug localizado, la vía breve descrita abajo puede sustituir los tres documentos de corte.

### Dónde queda el plan, el presente y la historia

| Archivo | Contenido | Cuándo leerlo | Cuándo escribirlo |
| --- | --- | --- | --- |
| [roadmap.md](roadmap.md) | Hitos, orden y puertas de salida. Es el **plan**. | Al escoger el siguiente hito o comprobar su puerta. | Si cambia el plan o los criterios de salida; no para anotar progreso diario. |
| [project-state.md](project-state.md) | Hito y corte activos, capacidad comprobada, bloqueos y siguiente acción. Es el **estado actual**. | Al comenzar una tarea o retomar el proyecto. | Cuando cambie cualquiera de esos datos; se reemplaza la foto anterior. |
| `docs/work/<slug>/tasks.md` | Progreso concreto de las tareas del **corte**. | Al ejecutar o retomar ese corte. | Al completar, descubrir o replanificar una tarea. |
| [implementation-log.md](implementation-log.md) | Entradas cronológicas legibles por una persona: cambio, motivo, comprobaciones reales con resultado y pendientes. Es el **historial**. | Si se pide la historia o se investiga un problema. No hace falta cargarlo al iniciar cada tarea. | Al cerrar trabajo significativo; se añade una entrada, con la más reciente arriba. |

Por ejemplo, al empezar el primer webhook se consulta `project-state.md` para saber que el hito 0 aún está pendiente. Si el hito 0 no ha superado su puerta, se termina primero o se deja explícita la dependencia. Tras una entrega significativa, `tasks.md` refleja las tareas comprobadas, `project-state.md` muestra el siguiente paso y `implementation-log.md` registra qué cambió, por qué, qué pruebas se ejecutaron y qué quedó pendiente. `roadmap.md` solo cambia si cambió el plan.

## 1. Qué carga Codex al abrir el proyecto

Inicia Codex en la raíz de EventFlow o en una subcarpeta del repositorio Git. Codex construye su cadena de instrucciones al iniciar la sesión: lee las instrucciones globales aplicables y [AGENTS.md](../AGENTS.md), además de posibles instrucciones más cercanas a la carpeta actual. También descubre las **descripciones** de las skills en `.agents/skills/`; lee el contenido completo de una skill cuando se invoca explícitamente o la selecciona para una tarea adecuada. Si cambias `AGENTS.md` durante una sesión, abre una sesión nueva para comprobar cómo se carga.

| Archivo | Cuándo entra en juego | Para qué sirve |
| --- | --- | --- |
| [AGENTS.md](../AGENTS.md) | Codex lo carga al iniciar. | Invariantes que aplican a casi toda tarea: durabilidad, aislamiento, duplicados, SSRF, secretos y cierre con pruebas. |
| [README.md](../README.md) | Se consulta al orientarse o buscar comandos. | Mapa del proyecto y comandos **cuando existan**. |
| [docs/spec.md](spec.md) | Al definir o comprobar comportamiento. | Requisitos EF-01…EF-14, criterios de aceptación y escenarios finales. Es la referencia funcional vigente. |
| [docs/architecture.md](architecture.md) | Al diseñar datos, procesos, seguridad o fallos. | Contratos técnicos: outbox, fuente de verdad, leases, reintentos, tenant y SSRF. |
| [docs/roadmap.md](roadmap.md) | Al seleccionar y cerrar un hito. | Orden de implementación y puerta observable de cada hito. |
| [docs/project-state.md](project-state.md) | Al iniciar una tarea y cuando cambia el trabajo activo. | Foto breve del hito actual, avance comprobado, bloqueos y próximo paso. |
| [docs/implementation-log.md](implementation-log.md) | Se escribe tras trabajo significativo; se lee solo si alguien pide historia o investiga un incidente. | Cronología legible para una persona: qué se hizo, por qué, qué se comprobó y qué quedó pendiente. |
| [docs/decisions.md](decisions.md) | Cuando una decisión afecta la implementación. | Decisiones D ya adoptadas y cuestiones P pendientes con el momento en que deben cerrarse. |
| [docs/source/eventflow_project_dossier.md](source/eventflow_project_dossier.md) | Solo para rastrear la propuesta original. | Material archivado; sus etiquetas `DECIDED` no prevalecen sobre la especificación revisada. |

Los documentos enlazados **no se cargan todos automáticamente**. `AGENTS.md` y las skills indican qué consultar. Esto evita que el dossier extenso consuma contexto en cada petición. La [documentación de OpenAI sobre AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) explica el descubrimiento; la [guía de skills](https://learn.chatgpt.com/docs/build-skills) describe su carga progresiva.

## 2. De una petición a una especificación del corte

El agente empieza por consultar `docs/project-state.md`, leer la petición, localizar el hito y los requisitos EF afectados, e inspeccionar el código y las pruebas existentes. Por ejemplo, «implementar el primer webhook firmado» corresponde al hito 1 y afecta al menos EF-02, EF-04 y EF-05. Después comprueba las invariantes de arquitectura y si alguna decisión P bloquea el trabajo. Para destinos HTTP aportados por usuarios, P-03 debe cerrarse antes de permitir el envío. No necesita leer el log histórico para orientarse.

Para una funcionalidad o un cambio transversal se usa [$eventflow-slice](../.agents/skills/eventflow-slice/SKILL.md). Puedes invocarla expresamente en Codex con `$eventflow-slice`; Codex también puede seleccionarla por su descripción. La skill crea o actualiza `docs/work/<slug>/`:

| Artefacto del corte | Pregunta que responde |
| --- | --- |
| `spec.md` | ¿Qué comportamiento observable se pide, qué IDs EF cubre y qué fallos deben probarse? |
| `plan.md` | ¿Qué componentes y datos cambian, qué migración o decisión se necesita y cómo se comprobará? |
| `tasks.md` | ¿Qué unidades pequeñas de código, pruebas y documentación quedan pendientes o hechas? |

`docs/work/` todavía no existe porque se crea con el primer corte amplio. Un bug localizado sigue una vía más corta: causa, corrección y verificación, sin producir tres documentos por rutina. Una decisión abierta se registra en `docs/decisions.md` con motivo y prueba antes de codificar la parte dependiente.

## 3. Implementar, comprobar y converger

El agente implementa un grupo pequeño de tareas, actualiza `tasks.md` y ejecuta las comprobaciones que **ya existan** en el repositorio. Si cambia persistencia, añade una migración Alembic y prueba su aplicación. Si toca entregas o seguridad, prepara pruebas de los fallos relevantes, no solo del caso feliz. Al final compara código y resultados con los escenarios de `docs/work/<slug>/spec.md` y los requisitos EF originales. Si encuentra un hueco, lo añade a `tasks.md`, lo corrige y repite la comprobación. Esto es la fase de convergencia: el corte no se cierra porque todas las tareas estén marcadas, sino porque la conducta exigida se observa.

Al terminar trabajo significativo, actualiza la foto en `docs/project-state.md` y añade una entrada a `docs/implementation-log.md` con cambio, motivo, validaciones reales y pendientes. El log ayuda a una persona a reconstruir qué pasó; no es una lista de instrucciones ni una fuente que Codex deba releer en cada sesión.

Cuando el cambio afecta ingesta, entregas, workers, autenticación o webhooks, se usa [$eventflow-reliability-review](../.agents/skills/eventflow-reliability-review/SKILL.md) antes del cierre. Revisa el diff y las pruebas en busca de pérdida de trabajo, carreras, duplicados, accesos entre tenants, secretos y SSRF. Es una **skill de revisión**, no una comprobación automática de CI: hay que invocarla o pedir la revisión de forma explícita si Codex no la selecciona.

### Matriz de verificación por riesgo

Esta matriz reúne criterios ya definidos en la especificación y la arquitectura. Indica qué evidencia debe buscar cada corte; **no es todavía un test runner**.

| Riesgo | Requisitos | Evidencia esperada |
| --- | --- | --- |
| Evento aceptado pero trabajo perdido | EF-02, EF-05 | Transacción Event/Delivery/outbox; prueba de fallo de Redis tras commit y recuperación del aviso pendiente. |
| Ingesta o ejecución duplicada | EF-03, EF-05 | Restricciones de unicidad, conflicto `409`, dos peticiones/worker concurrentes y estado de intentos coherente. |
| Entrega y reintento incorrectos | EF-04, EF-06, EF-07 | Receptor de prueba verifica bytes firmados, secuencia 503→200, dead letter y replay sin borrar historial. |
| Límite de salida ignorado | EF-06, EF-13 | Dos workers respetan pausa `Retry-After` y concurrencia por endpoint; otro destino sigue avanzando. |
| Destino o tenant inseguro | EF-01, EF-08 | Pruebas de acceso cruzado y destinos IPv4/IPv6 internos, DNS cambiante, redirecciones y proxies. |
| Sistema difícil de operar o demostrar | EF-09, EF-10 | UI responsive y accesible para escenarios reales, API de consulta, IDs correlacionados, estados/latencias visibles, métricas de backlog y logs sin secretos. |
| Entorno, VPS o rendimiento irreproducible | EF-11, EF-12, EF-14 | Instalación limpia, CI y build frontend; benchmark documentado; despliegue real en Ubuntu 24.04 con HTTPS, persistencia, restauración y recorrido desde navegador. |

La puerta de cada hito en `docs/roadmap.md` decide **cuándo** debe existir esa evidencia. En el hito 0 se establecen comandos reales de pruebas, lint y tipos; en el hito 1 se demuestra recuperación desde PostgreSQL incluso tras perder un aviso publicado; en el hito 2 se prueban los límites agregados de salida; en el hito 4 se comprueban UI, API y métricas; en el hito 6 se verifica la ejecución real en el VPS. No se deben declarar como ejecutadas pruebas o comandos que aún no existen.

## 4. Ejemplo de flujo completo: primer webhook

1. Pides: «Usa `$eventflow-slice` para el primer recorrido `order.created` del hito 1».
2. El agente lee EF-02/04/05, arquitectura y hoja de ruta; examina backend y tests. Si va a aceptar URLs arbitrarias, resuelve antes P-03 (SSRF). Puede empezar con el receptor HTTP local aislado de pruebas.
3. Crea `docs/work/primer-webhook/spec.md`, `plan.md` y `tasks.md`. La aceptación incluye: `202` solo después del commit, firma verificable, entrega exitosa y trabajo recuperable si Redis falla tras aceptar el evento o se pierde un aviso ya publicado.
4. Cierra P-04 antes del primer worker. Implementa API, transacción, outbox, despachador, reclamo/lease mínimo, reconciliador, worker y receptor de prueba en cambios revisables; añade migraciones y pruebas correspondientes.
5. Ejecuta pruebas unitarias, de integración con PostgreSQL/Redis y de extremo a extremo disponibles; pasa lint y tipos si ya existen. Anota fallos de entorno y tareas incompletas.
6. Pide la revisión de fiabilidad. Corrige hallazgos y compara el resultado con cada criterio del corte y la puerta del hito 1.
7. Actualiza `tasks.md`, decisiones y `docs/project-state.md`; añade una entrada humana a `docs/implementation-log.md`. Entrega un resumen con requisitos EF cubiertos, archivos, comandos/resultados, garantías demostradas y límites pendientes.

El hito 2 repite este ciclo para reintentos, duplicados, concurrencia, límites de salida, dead letter y replay. Los hitos posteriores añaden autorización backend, límites de ingesta, interfaz responsive para ejecutar escenarios y medición sin perder las garantías ya demostradas. El cierre del MVP exige repetir la demo en un VPS Ubuntu 24.04 LTS. Solo la matriz completa de miembros/roles queda como ampliación opcional.

## 5. Cómo se evalúa el propio harness

[docs/harness-evals.md](harness-evals.md) contiene siete situaciones para sesiones nuevas de Codex, incluidas la recuperación tras fallo del broker, los límites de salida y la demo visual en VPS. Se revisa si el agente tomó decisiones correctas y produjo evidencia; no se aprueba por recitar instrucciones. Estos casos se usan al cambiar el harness, de forma selectiva según el alcance. Aún no se han ejecutado como una suite automatizada ni sustituyen los tests de la aplicación.

En resumen: `AGENTS.md` mantiene reglas siempre presentes; `spec.md` dice **qué** debe ocurrir; `architecture.md` restringe **cómo** preservar las garantías; `roadmap.md` ordena **cuándo** abordar cada hito; `project-state.md` dice **dónde estamos ahora**; `implementation-log.md` explica a una persona **qué se hizo**; las skills guían la ejecución y revisión, y las pruebas aportan evidencia para cerrar cada corte.
