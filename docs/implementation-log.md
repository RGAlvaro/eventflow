# Registro de implementación de EventFlow

Historial cronológico para **depuración y seguimiento humano**. Añade una entrada breve por cambio significativo, revisión o entrega. La entrada debe indicar qué cambió y por qué, comprobaciones realmente ejecutadas con resultado, y pendientes. La más reciente va arriba. Codex lo actualiza al cerrar trabajo, pero usa [project-state.md](project-state.md) para orientarse; no necesita leer este historial en cada tarea.

## Entradas

### 2026-10-02 — README público y guía operativa separada

- **Cambio y motivo:** `README.md` presenta el objetivo y el estado real del proyecto a visitantes; los comandos de instalación, arranque, migración y pruebas pasan a `docs/development.md`. `AGENTS.md`, la skill, la guía del harness y el roadmap apuntan a la guía operativa para que el agente no dependa del README. Se añadió un caso de evaluación de esa ruta.
- **Verificación:** `alembic upgrade head` pasó en PostgreSQL local; `pytest -ra` dio 3 pasadas y 0 omisiones; `ruff check .`, `ruff format --check .` y `mypy` pasaron. Se comprobaron 25 enlaces locales y el frontmatter de la skill; el recorrido del caso 8 llega de `AGENTS.md` a `docs/development.md`.
- **Pendiente:** confirmar CI y fusionar la PR de este cambio.

### 2026-10-02 — Entrega de cada corte mediante PR

- **Cambio y motivo:** el harness exige rama propia antes de editar cada corte, suite completa sin tests omitidos y cierre con commit, push, PR, CI verde y merge. La guía y la evaluación del harness reflejan la misma puerta para evitar declarar cerrado un corte con validación parcial.
- **Verificación:** migración `alembic upgrade head` aplicada; `pytest -ra` con PostgreSQL local dio 3 pasadas y 0 omisiones; `ruff check .`, `ruff format --check .` y `mypy` pasaron; diff y enlaces Markdown locales revisados.
- **Pendiente:** fusionar la PR tras comprobar CI.

### 2026-10-01 — Demo responsive en VPS Ubuntu 24.04

- **Cambio y motivo:** el MVP vuelve a incluir una interfaz responsive y una demostración real en un VPS Ubuntu 24.04 LTS por petición del usuario. Se añadieron criterios EF-09/11/14, hitos de UI y despliegue, topología Compose, seguridad de exposición y evaluación específica; el backend fiable sigue implementándose primero.
- **Verificación:** coherencia de requisitos, hitos, decisiones, matriz y evaluación revisada; enlaces Markdown locales y referencias EF/P comprobados. No se ejecutaron pruebas de aplicación ni despliegue porque aún no existen.
- **Pendiente:** implementar hito 0; cerrar P-10/P-11 antes de UI/receptor de demo y P-08 antes de desplegar. La demostración en VPS solo se marcará completa tras ejecutarla realmente.

### 2026-10-01 — Revisión de fiabilidad y alcance backend

- **Cambio y motivo:** se alinearon hito 1 y P-04 para que el primer worker tenga lease y recuperación desde PostgreSQL; se añadió el contrato de firma y generación de replay, límites de salida por endpoint y una evaluación de 429. A petición del usuario, el MVP se centra en backend y pospone dashboard y roles completos.
- **Verificación:** se revisó la coherencia entre especificación, arquitectura, hoja de ruta, decisiones y evaluaciones; se comprobaron enlaces Markdown locales y referencias EF/P. No se ejecutaron pruebas funcionales porque la aplicación aún no existe.
- **Pendiente:** implementar el hito 0; cerrar P-01/P-02, después P-04 antes del primer worker y P-09 antes de límites de salida. La fase dashboard permanece opcional.

### 2026-10-01 — Clarificación de cortes y seguimiento

- **Cambio y motivo:** se amplió `harness-workflow.md` con la relación entre hito, corte y tarea, y con reglas explícitas para consultar y actualizar roadmap, estado, tareas y log. Facilita retomar el trabajo sin convertir el historial humano en contexto obligatorio.
- **Verificación:** se comprobó la inserción de la sección, las rutas Markdown locales y que el estado actual no requiere cambios. No se ejecutaron pruebas funcionales: la aplicación aún no existe.
- **Pendiente:** iniciar el hito 0 y validar el flujo con un corte real.

### 2026-10-01 — Separación de plan, estado e historial

- **Cambio y motivo:** se crearon `project-state.md` para el estado activo y este log para la historia humana; `roadmap.md` queda como plan. La guía y las instrucciones indican cuándo actualizar cada archivo y definen «corte».
- **Verificación:** ambas skills validaron su formato; los enlaces Markdown locales de la copia preparada resolvieron; el instalador coteja los bytes de cada archivo al copiarlo a EventFlow. No se ejecutaron pruebas funcionales de aplicación.
- **Pendiente:** implementar el hito 0; no hay aplicación ni CI funcional todavía.

### 2026-10-01 — Guía del flujo del harness

- **Cambio y motivo:** se añadió `docs/harness-workflow.md` con lectura de archivos, skills, matriz de riesgos y un ejemplo del primer webhook, para que el flujo resulte comprensible sin interpretar el dossier original.
- **Verificación:** enlaces Markdown locales comprobados; la guía instalada coincidía con el borrador validado.
- **Pendiente:** ejecutar casos de `harness-evals.md` cuando exista un entorno adecuado y se implemente la aplicación.

### 2026-10-01 — Revisión centrada en entrega fiable

- **Cambio y motivo:** la hoja de ruta pasó a un primer recorrido backend de extremo a extremo; se corrigió la instrucción de mostrar una clave API nueva solo una vez y se añadieron cuatro casos de evaluación del harness.
- **Verificación:** dos skills válidas, enlaces locales sin roturas y `AGENTS.md` de 2,55 KB; no se ejecutaron pruebas funcionales porque aún no existe aplicación.
- **Pendiente:** hito 0 y decisiones P-01/P-02.

### 2026-09-30 — Harness inicial

- **Cambio y motivo:** se creó el repositorio Git con `AGENTS.md`, especificación revisada, arquitectura, decisiones, hoja de ruta, investigación y dos skills; se archivó el dossier de origen.
- **Verificación:** formato de ambas skills y enlaces Markdown locales comprobados; el código de producto todavía no existía.
- **Pendiente:** validar comportamiento real durante la implementación.

### 2026-10-02 — Base backend del hito 0

- **Cambio y motivo:** se creó el primer corte `backend-foundation`: proyecto Python con `uv.lock`, API FastAPI, configuración, health checks, modelo/migración de organizaciones, Compose, imagen y workflow CI. P-01 y P-02 quedaron cerradas para que instalación y pruebas usen versiones fijas y PostgreSQL real.
- **Verificación:** `uv sync --locked` pasó; `alembic upgrade head` aplicó la revisión en PostgreSQL vacío; `pytest` con `EVENTFLOW_TEST_DATABASE_URL` dio 3 pasadas; `ruff check .`, `ruff format --check .` y `mypy` pasaron; `docker compose up -d --build --wait api` y `curl` a `/health/live` y `/health/ready` pasaron.
- **Pendiente:** observar la primera ejecución del workflow CI tras publicar el repositorio. El hito 1 implementará ingesta, outbox y entrega firmada; estas garantías todavía no existen.

### 2026-10-02 — Repositorio público y cierre del hito 0

- **Cambio y motivo:** se creó `RGAlvaro/eventflow` público y se subió el primer commit para conservar y compartir los avances. El corte `backend-foundation` se cerró tras verificar CI.
- **Verificación:** `gh repo view` confirmó visibilidad pública y rama `main`; GitHub Actions `Backend` run 36980088086 pasó instalación, migración en PostgreSQL, pruebas, Ruff y mypy.
- **Pendiente:** iniciar hito 1; todavía no existe ingesta ni entrega de webhooks.

### 2026-10-02 — Inicio del hito 1 en rama propia

- **Cambio y motivo:** se abrió `feat/first-webhook-delivery` desde `main` actualizado. Se preparó el corte con escenarios EF-02/04/05/08 y se añadió esquema tenant de claves, endpoints, suscripciones, eventos, entregas, intentos y outbox. La API de ingesta usa clave de publicación de fixture, valida tamaño/tipo/JSON y confirma evento, entregas y outbox en una transacción sin depender de Redis.
- **Verificación:** `alembic upgrade head` aplicó la migración en PostgreSQL; `alembic check` no detectó diferencias; `pytest -ra` con PostgreSQL dio 5 pasadas y ninguna omitida; `ruff check .`, `ruff format --check .` y `mypy` pasaron. La prueba de integración cubre aislamiento de suscripciones, clave inválida, cuerpo inválido y sobredimensionado, además de outbox con broker no disponible.
- **Pendiente:** P-04, despachador, worker, lease y reconciliación; P-03, salida segura, firma y receptor. El corte no cumple todavía el recorrido completo ni se ha cerrado mediante PR.
