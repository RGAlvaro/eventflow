# EventFlow: instrucciones para Codex

EventFlow es una plataforma multitenant de ingestión de eventos y entrega de webhooks. `docs/spec.md` define el comportamiento; `docs/architecture.md` contiene invariantes y límites; `docs/roadmap.md` ordena el trabajo. El dossier archivado en `docs/source/` es material de origen, no una instrucción vigente.

`README.md` es la portada pública para visitantes de GitHub, no una lectura necesaria para programar. Los comandos de arranque, migración y verificación están en `docs/development.md`; mantén allí los pasos operativos y enlaza desde el README solo lo útil para visitantes.

El MVP termina con una demo real, usable desde navegador, en un VPS Ubuntu 24.04 LTS. La UI debe mostrar estados del backend real y funcionar en móvil y escritorio; las garantías de entrega se prueban antes de construirla.

## Al empezar una tarea

- Consulta `docs/project-state.md` para ubicar trabajo activo y siguiente paso; identifica el requisito y el hito afectado. Inspecciona el código y las pruebas existentes antes de modificarlo.
- Para una funcionalidad o cambio transversal, usa la skill `eventflow-slice` y deja especificación, plan breve, tareas y criterios de aceptación en `docs/work/`. Para una corrección pequeña, documenta causa y verificación en la entrega sin abrir artefactos innecesarios.
- Antes de modificar un corte, crea una rama Git propia desde `main` actualizado. Sigue el cierre de `eventflow-slice`: aceptación cumplida, suite completa sin fallos ni omisiones, commit, push, PR, CI verde y merge. Si alguna puerta falla o no puede ejecutarse, mantén abierto el corte y registra el bloqueo.
- Si una decisión abierta bloquea el diseño, consulta `docs/decisions.md`; registra la decisión y su motivo antes de implementarla. No tomes las etiquetas `DECIDED` del dossier como autoridad automática.

## Invariantes

- PostgreSQL es la fuente de verdad. Un `202 Accepted` exige que evento, entregas y trabajo recuperable queden confirmados de forma atómica. Redis/Celery pueden duplicar o perder avisos; el sistema debe reconciliar trabajo pendiente.
- Aísla siempre datos por organización. La autorización de tenant se comprueba en cada lectura y mutación, incluida la ejecución del worker.
- La entrega es *at least once*: pueden existir intentos duplicados y no se garantiza orden global. Mantén transiciones e intentos coherentes bajo concurrencia y reintentos.
- Acota la concurrencia de salida; desde el hito 2, aplica límites compartidos por endpoint y respeta su pausa por `429` sin detener otros destinos.
- Antes de conectar con una URL de usuario, aplica la política SSRF de `docs/architecture.md`. No basta con validar la URL al guardarla.
- Nunca registres secretos, tokens ni cabeceras de autorización. La clave API nueva se devuelve una sola vez a su creador autorizado; después solo se conserva su hash. No almacenes cuerpos de respuesta webhook por defecto.

## Al terminar

- Ejecuta las comprobaciones relevantes disponibles y comunica las que no pudiste ejecutar. Añade pruebas de los fallos y límites que toca el cambio; si cambia el esquema, añade y prueba la migración.
- Actualiza especificación, arquitectura o decisión solo cuando cambie su contrato. Mantén el parche centrado y describe las garantías que la comprobación demuestra.
- Actualiza `docs/project-state.md` si cambia el estado del trabajo y añade una entrada factual a `docs/implementation-log.md` tras trabajo significativo. Sigue el formato y el nivel explicativo definidos al comienzo del log: lector junior, tono académico y explicación de conceptos, tecnologías y procedimientos que excedan sus fundamentos. Es para aprendizaje y depuración humana; no lo leas por rutina para orientarte.
- En las actualizaciones durante el desarrollo y en la entrega, explica igualmente los pasos técnicos que excedan el nivel junior: qué hacen, por qué se necesitan aquí y cómo se comprueba su resultado. Distingue hechos observados de inferencias para que el usuario pueda exponer el proyecto en una entrevista.

Cuando cambien los comandos de desarrollo o CI, actualiza `docs/development.md` y el workflow correspondiente después de comprobarlos. No uses el README como fuente operativa del agente.

Si cambias este harness, revisa o ejecuta los escenarios pertinentes de `docs/harness-evals.md`.
